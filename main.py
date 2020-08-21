import torch
from torch.autograd import Variable as V
import torchvision.models as models
from torchvision import transforms as trn
from torch.nn import functional as F
import os
import numpy as np
import cv2
from PIL import Image
import json
from kafka import KafkaConsumer
from kafka import KafkaProducer
from json import loads
from base64 import decodestring
import base64
from dotenv import load_dotenv
import uuid
import redis

load_dotenv()

TOPIC = "TORCH_PLACES_365"
KAFKA_HOSTNAME = os.getenv("KAFKA_HOSTNAME")
KAFKA_PORT = os.getenv("KAFKA_PORT")
RECEIVE_TOPIC = "TORCH_PLACES_365"
SEND_TOPIC_FULL = "IMAGE_RESULTS"
SEND_TOPIC_TEXT = "TEXT"
print("kafka : "+KAFKA_HOSTNAME+':'+KAFKA_PORT)
REDIS_HOSTNAME = os.getenv("REDIS_HOSTNAME")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

r = redis.StrictRedis(host=REDIS_HOSTNAME, port=REDIS_PORT,
                      password=REDIS_PASSWORD, ssl=True)

r.set(TOPIC, "FREE")
consumer_torch_places_365 = KafkaConsumer(
    RECEIVE_TOPIC,
    bootstrap_servers=[KAFKA_HOSTNAME+':'+KAFKA_PORT],
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id="my-group",
    value_deserializer=lambda x: loads(x.decode("utf-8")),
)

# For Sending processed img data further
producer = KafkaProducer(
    bootstrap_servers=[KAFKA_HOSTNAME+':'+KAFKA_PORT],
    value_serializer=lambda x: json.dumps(x).encode("utf-8"),
)


def load_labels():
    # prepare all the labels
    # scene category relevant
    file_name_category = 'categories_places365.txt'
    if not os.access(file_name_category, os.W_OK):
        synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/categories_places365.txt'
        os.system('wget ' + synset_url)
    classes = list()
    with open(file_name_category) as class_file:
        for line in class_file:
            classes.append(line.strip().split(' ')[0][3:])
    classes = tuple(classes)

    # indoor and outdoor relevant
    file_name_IO = 'IO_places365.txt'
    if not os.access(file_name_IO, os.W_OK):
        synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/IO_places365.txt'
        os.system('wget ' + synset_url)
    with open(file_name_IO) as f:
        lines = f.readlines()
        labels_IO = []
        for line in lines:
            items = line.rstrip().split()
            labels_IO.append(int(items[-1]) -1) # 0 is indoor, 1 is outdoor
    labels_IO = np.array(labels_IO)

    # scene attribute relevant
    file_name_attribute = 'labels_sunattribute.txt'
    if not os.access(file_name_attribute, os.W_OK):
        synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/labels_sunattribute.txt'
        os.system('wget ' + synset_url)
    with open(file_name_attribute) as f:
        lines = f.readlines()
        labels_attribute = [item.rstrip() for item in lines]
    file_name_W = 'W_sceneattribute_wideresnet18.npy'
    if not os.access(file_name_W, os.W_OK):
        synset_url = 'http://places2.csail.mit.edu/models_places365/W_sceneattribute_wideresnet18.npy'
        os.system('wget ' + synset_url)
    W_attribute = np.load(file_name_W)

    return classes, labels_IO, labels_attribute, W_attribute

def hook_feature(module, input, output):
    features_blobs.append(np.squeeze(output.data.cpu().numpy()))

def returnCAM(feature_conv, weight_softmax, class_idx):
    # generate the class activation maps upsample to 256x256
    size_upsample = (256, 256)
    nc, h, w = feature_conv.shape
    output_cam = []
    for idx in class_idx:
        cam = weight_softmax[class_idx].dot(feature_conv.reshape((nc, h*w)))
        cam = cam.reshape(h, w)
        cam = cam - np.min(cam)
        cam_img = cam / np.max(cam)
        cam_img = np.uint8(255 * cam_img)
        output_cam.append(cv2.resize(cam_img, size_upsample))
    return output_cam
def returnTF():
# load the image transformer
    tf = trn.Compose([
        trn.Resize((224,224)),
        trn.ToTensor(),
        trn.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    return tf

def load_model():
    # this model has a last conv feature map as 14x14

    model_file = 'wideresnet18_places365.pth.tar'
    if not os.access(model_file, os.W_OK):
        os.system('wget http://places2.csail.mit.edu/models_places365/' + model_file)
        os.system('wget https://raw.githubusercontent.com/csailvision/places365/master/wideresnet.py')

    import wideresnet
    model = wideresnet.resnet18(num_classes=365)
    checkpoint = torch.load(model_file, map_location=lambda storage, loc: storage)
    state_dict = {str.replace(k,'module.',''): v for k,v in checkpoint['state_dict'].items()}
    model.load_state_dict(state_dict)
    model.eval()
    # hook the feature extractor
    features_names = ['layer4', 'avgpool']  # this is the last conv layer of the resnet
    for name in features_names:
        model._modules.get(name).register_forward_hook(hook_feature)
    return model

# load the labels
classes, labels_IO, labels_attribute, W_attribute = load_labels()

# load the model
features_blobs = []
model = load_model()

# load the transformer
tf = returnTF() # image transformer

# get the softmax weight
params = list(model.parameters())
weight_softmax = params[-2].data.numpy()
weight_softmax[weight_softmax<0] = 0


if __name__ == '__main__':
    print("in main")
    for message in consumer_torch_places_365:
        print('xxx--- inside torch_places_365---xxx')
        print(KAFKA_HOSTNAME + ':' + KAFKA_PORT)
        message = message.value
        print("MESSAGE RECEIVED torch_places_365: ")
        image_id = message['image_id']
        data = message['data']
        r.set(RECEIVE_TOPIC, image_id)
        image_file = str(uuid.uuid4()) + ".jpg"
        with open(image_file, "wb") as fh:
            fh.write(base64.b64decode(data.encode("ascii")))
        img = Image.open(image_file)
        input_img = V(tf(img).unsqueeze(0))

        # forward pass
        logit = model.forward(input_img)
        h_x = F.softmax(logit, 1).data.squeeze()
        probs, idx = h_x.sort(0, True)
        probs = probs.numpy()
        idx = idx.numpy()

        print('RESULT ON')
        # output the IO prediction
        io_image = np.mean(labels_IO[idx[:10]])  # vote for the indoor or outdoor
        if io_image < 0.5:
            env_type = 'indoor'
        else:
            env_type = 'outdoor'

        labels = []
        scores = []

        # output the prediction of scene category
        print('--SCENE CATEGORIES:')
        for i in range(0, 5):
            scores.append(probs[i])
            labels.append(classes[idx[i]])
            print('{:.3f} -> {}'.format(probs[i], classes[idx[i]]))

        # output the scene attributes
        responses_attribute = W_attribute.dot(features_blobs[1])
        idx_a = np.argsort(responses_attribute)
        scene_attributes = [labels_attribute[idx_a[i]] for i in range(-1, -10, -1)]

        # generate class activation mapping
        print('Class activation map is saved as cam.jpg')
        CAMs = returnCAM(features_blobs[0], weight_softmax, [idx[0]])
        scores = [float(np_float) for np_float in scores]
        full_results_dict = {
            "image_id": image_id,
            "Environment_type" : env_type,
            "scene_recog" : {
                "labels": labels,
                "scores": scores
            },
            "scene_atrributes" : scene_attributes
        }
        text_results = {
            "image_id": image_id,
            "Environment_type": env_type,
            "scene_recog": {
                "labels": labels,
                "scores": scores
            },
            "scene_atrributes": scene_attributes
        }
        producer.send(SEND_TOPIC_FULL, value=json.dumps(full_results_dict))
        producer.send(SEND_TOPIC_TEXT, value=json.dumps(text_results))
        producer.flush()
