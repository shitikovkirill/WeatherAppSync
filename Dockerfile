FROM python:3.6

ARG CDK=1.17.1

WORKDIR /project

RUN set -ex \
 && apt-get update \
 && apt-get install nodejs npm -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g aws-cdk@$CDK

COPY . .

RUN set -ex \
 && pip3 install -r requirements.txt

CMD ["/usr/local/bin/cdk"]