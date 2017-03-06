#!/usr/bin/env python3

import uuid

import datetime
import time

# Configuration
bucket = 'iot-mpg-is' #Make sure you have permissions to Put, Delete and Get.
path = "nullid/picam-" #The prefix of the pictures.
maxb = 75 # The max brightness of the pictures
period = 60
topic = "arn:aws:sns:eu-west-1:384599271648:iot-nullid-taco"

print("Initializing...")

import picamera
import boto3

camera = picamera.PiCamera()
s3 = boto3.client('s3')
rek = boto3.client('rekognition')
sns = boto3.client('sns')

print("Initialization done!")


while True:
  now = datetime.datetime.now()
  camera.brightness = int(min(maxb,abs((now.hour - 12)/24)*maxb + 50)) #Make it more bright at night

  print("Taking picture...")
  camera.capture("/tmp/picam.jpg")

  objname = '{}{}.jpg'.format(path, str(uuid.uuid4())[-8:])

  print('Uploading as {}...'.format(objname))

  s3.upload_file('/tmp/picam.jpg', bucket,objname)
  print("Done!")

  print("Rekognizing...")

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
  print(LabelMap)
  if 'Cat' in LabelMap:
    print("Kitty sighted! Notifying!")
    sns.publish(TopicArn=topic, Message="TACOS Alert! Kitty detected in {}".format(objname))
  else:
    print("No cat detected... :(")
    print("Deleting non-kitty picture")
    s3.delete_object(Bucket=bucket, Key=objname)
  print("Waiting for {} seconds to try again".format(period)) 
  time.sleep(period)

