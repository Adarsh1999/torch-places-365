import json
from db_models.mongo_setup import global_init
from db_models.models.cache_model import Cache
import uuid
import globals
import init
from scene_recog_service import predict
import pyfiglet
import requests

global_init()

def save_to_db(db_object, labels, scores):
    print("in save")
    print(db_object)
    print(db_object.id)
    db_object.labels = labels
    db_object.scores = scores
    db_object.save()

def update_state(file):
    payload = {
        'topic_name': globals.RECEIVE_TOPIC,
        'client_id': globals.CLIENT_ID,
        'value': file
    }
    requests.request("POST", globals.DASHBOARD_URL,  data=payload)


if __name__ == '__main__':
    print(pyfiglet.figlet_format(str(globals.RECEIVE_TOPIC)))
    print(pyfiglet.figlet_format("INDEXING CONTAINER"))
    print("Connected to Kafka at " + globals.KAFKA_HOSTNAME + ":" + globals.KAFKA_PORT)
    print("Kafka Consumer topic for this Container is " + globals.RECEIVE_TOPIC)
    for message in init.consumer_obj:
        global_init()
        message = message.value
        db_key = str(message)
        db_object = Cache.objects.get(pk=db_key)
        file_name = db_object.file_name
        # init.redis_obj.set(globals.RECEIVE_TOPIC, file_name)
        print("#############################################")
        print("########## PROCESSING FILE " + file_name)
        print("#############################################")
        if db_object.is_doc_type:
            """document"""
            if db_object.contains_images:
                images_array = []
                for image in db_object.files:
                    pdf_image = str(uuid.uuid4()) + ".jpg"
                    with open(pdf_image, 'wb') as file_to_save:
                        file_to_save.write(image.file.read())
                    images_array.append(pdf_image)
                to_save  = []
                final_labels=db_object.labels
                final_scores=db_object.scores
                for image in images_array:
                    response = predict(file_name=image)
                    # final_labels.extend(response["labels"])
                    for label,score in zip(response["labels"],response['scores']):
                        if label not in final_labels:
                            final_labels.append(label)
                            final_scores.append(score)
                        else:
                            x = final_labels.index(label)
                            score_to_check = final_scores[x]
                            if score > score_to_check:
                                final_scores[x] = score


                save_to_db(db_object,final_labels,final_scores)
                print(".....................FINISHED PROCESSING FILE.....................")
                update_state(file_name)

        else:
            """image"""

            with open(file_name, 'wb') as file_to_save:
                file_to_save.write(db_object.file.read())
            image_result = predict(file_name)
            labels=image_result['labels']
            scores=image_result['scores']
            save_to_db(db_object,labels,scores)
            print(".....................FINISHED PROCESSING FILE.....................")
            update_state(file_name)
