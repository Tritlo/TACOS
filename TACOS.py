#!/usr/bin/env python3

import uuid

import datetime
import time
import logging
import json

# Configuration
bucket = 'iot-mpg-is' #Make sure you have permissions to Put, Delete and Get.
path = 'nullid/picam-' #The prefix of the pictures.
maxb = 75 # The max brightness of the pictures
period = 60
topic = 'arn:aws:sns:eu-west-1:384599271648:iot-nullid-taco'

logger = logging.getLogger(__name__)
now = datetime.datetime.now()
logging.basicConfig(filename='taco-log-{}-{}-{}'.format(now.year,now.month,now.day),
                    format='%(asctime)s %(message)s',
                    level=logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)

logger.info('Initializing...')

import picamera
import boto3

camera = picamera.PiCamera()
s3 = boto3.client('s3')
rek = boto3.client('rekognition')
sns = boto3.client('sns')

logger.info('Initialization done!')

def letKnow(type, objname, LabelMap=None):
  logger.info('{} sighted! Notifying!'.format(type))
  s3.put_object_acl(ACL='public-read',Bucket=bucket,Key=objname)
  msg ='TACOS Alert! {} detected in {}! See it at {}. The labels were {}'.format(type,objname, link, json.dumps(LabelMap))
  sns.publish(TopicArn=topic, Message=msg)


while True:
  now = datetime.datetime.now()
  camera.brightness = int(min(maxb,abs((now.hour - 12)/24)*maxb + 50)) #Make it more bright at night
  logger.info(now)
  logger.info('Taking picture...')
  camera.capture('/tmp/picam.jpg')

  objname = '{}{}.jpg'.format(path, str(uuid.uuid4())[-8:])

  logger.info('Uploading as {}...'.format(objname))

  s3.upload_file('/tmp/picam.jpg', bucket,objname)
  logger.info('Done!')

  logger.info('Rekognizing...')

  res = rek.detect_labels(
          Image={
            'S3Object':{
              'Bucket': bucket,
              'Name': objname
           }},
        MaxLabels=10)

  labels = res['Labels']
  lks = map(lambda label: (label['Name'],label['Confidence']), labels)
  LabelMap = dict(lks)
  logger.info(LabelMap)
  link = 'https://s3-eu-west-1.amazonaws.com/{}/{}'.format(bucket,objname)
  if 'Cat' in LabelMap:
    letKnow('Kitty',objname)
  elif 'Animal' in LabelMap and (not ('Pet' in LabelMap) or LabelMap['Pet'] > 75):
     letKnow('Animal',objname, LabelMap)
  else:
    logger.info('No cat detected... :(')
    logger.info('Deleting non-kitty picture')
    s3.delete_object(Bucket=bucket, Key=objname)
  logger.info('Waiting for {} seconds to try again'.format(period)) 
  time.sleep(period)

