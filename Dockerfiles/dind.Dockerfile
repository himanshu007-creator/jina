FROM docker:20.10.13-git

RUN apk update && apk upgrade && apk --no-cache add curl bash make

CMD ["bash"]