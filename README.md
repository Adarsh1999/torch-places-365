## RUN IMAGE FROM GHCR

```sh
docker run -it --env-file .env --gpus all ghcr.io/semantic-search/torch-places-365:latest

```


To build the docker image locally, run:

```git
    git clone --recurse-submodules https://github.com/semantic-search/torch-places-365.git
```

```
docker build -t torch-places-365 .
```

```
docker run -it  --env-file .env --gpus all torch-places-365
```
