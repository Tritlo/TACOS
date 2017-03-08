#!/usr/bin/env python3

import datetime
import json
import logging
import os
import time
import uuid
from io import BytesIO

from PIL import Image

# Configuration
bucket = 'iot-mpg-is'  #Make sure you have permissions to Put, Delete and Get.
path = 'nullid/picam-'  #The prefix of the pictures.
maxb = 75  # The max brightness of the pictures
period = 0.25
topic = 'arn:aws:sns:eu-west-1:384599271648:iot-nullid-taco'
threshold = 10  # How much a pixel has to change to be noticed
sensitivity = 20  # How many changed pixels to count as 'motion'

logger = logging.getLogger(__name__)
now = datetime.datetime.now()
logging.basicConfig(filename='taco-log-{}-{}-{}'.format(now.year, now.month, now.day),
                    format='%(asctime)s %(message)s',
                    level=logging.INFO)

ch = logging.StreamHandler()
if os.getenv('DEBUG','False').lower() == 'true':
  ch.setLevel(logging.DEBUG)
else:
  ch.setLevel(logging.INFO)
logger.addHandler(ch)

logger.info('Initializing...')

import picamera  #isort:skip
import boto3  #isort:skip

camera = picamera.PiCamera()
s3 = boto3.client('s3')
rek = boto3.client('rekognition')
sns = boto3.client('sns')

logger.info('Initialization done!')


# Capture a small test image (for motion detection)
def captureTestImage():
  imageData = BytesIO()
  # what format is appropriate? does it matter?
  camera.capture(imageData, format='jpeg', resize=(100, 75))
  imageData.seek(0)
  image = Image.open(imageData)
  pixels = image.load()
  imageData.close()
  return image, pixels


# Returns a boolean that says whether the number of pixels that differ more than
# threshold between pixel access arrays im1 and im2 of width w and height h is
# greater than sensitivity
def pixelDiff(im1, im2, w, h, threshold):
  changedPixels = 0
  for x in range(w):
    for y in range(h):
       # Just check green channel as it's the highest quality channel
       pixdiff = abs(im1[x, y][1] - im2[x, y][1])
       if pixdiff > threshold:
         changedPixels += 1
  return changedPixels


def letKnow(type, objname, LabelMap=None):
  logger.info('{} sighted! Notifying!'.format(type))
  s3.put_object_acl(ACL='public-read', Bucket=bucket, Key=objname)
  msg = 'TACOS Alert! {} detected in {}! See it at {}. The labels were {}'.format(type, objname, link, json.dumps(LabelMap))
  sns.publish(TopicArn=topic, Message=msg)


# Capture higher quality image, run rekognize and save if there is an animal
def captureRekognizeSave():
  logger.info('Taking higher resolution picture...')
  camera.capture('/tmp/picam.jpg')
  os.system('jp2a --width=120 --color --border /tmp/picam.jpg')

  objname = '{}{}.jpg'.format(path, str(uuid.uuid4())[-8:])

  logger.info('Uploading as {}...'.format(objname))

  s3.upload_file('/tmp/picam.jpg', bucket, objname)
  logger.info('Done!')

  logger.info('Rekognizing...')

  res = rek.detect_labels(Image={'S3Object': {'Bucket': bucket, 'Name': objname}}, MaxLabels=10)

  labels = res['Labels']
  lks = map(lambda label: (label['Name'], label['Confidence']), labels)
  LabelMap = dict(lks)
  logger.info(LabelMap)
  link = 'https://s3-eu-west-1.amazonaws.com/{}/{}'.format(bucket, objname)
  if 'Cat' in LabelMap:
    letKnow('Kitty',objname)
  elif 'Animal' in LabelMap and (not ('Pet' in LabelMap) or LabelMap['Pet'] > 75):
     letKnow('Animal',objname, LabelMap)
  elif 'Face' in LabelMap:
     letKnow('Face',objname, LabelMap)
  else:
    logger.info('No cat detected... :(')
    logger.info('Deleting non-kitty picture')
    s3.delete_object(Bucket=bucket, Key=objname)


captureTestImage()
# Camera warmup time
time.sleep(2)
image1, buffer1 = captureTestImage()

def setCameraBrightness():
  '''Sets the camera brightness depending on the time of day. Returns a Boolean describing whether the brightness changed.'''
  now = datetime.datetime.now()

  oldbrightness = camera.brightness
  camera.brightness = int(min(maxb, abs((now.hour - 12) / 24) * maxb + 50))
  return (camera.brightness - oldbrightness) != 0

logger.info('Starting!')

while True:
  now = datetime.datetime.now()
  brightnessChanged = setCameraBrightness() # Make it more bright at night
  if brightnessChanged:
    # If the brightness changed, the comparison is useless, so we take another one.
    logger.info('Brightness changed, taking another one!')
    image1, buffer1 = captureTestImage()
    time.sleep(period)

  # Capture comparison image
  logger.debug('Taking picture for comparison...')
  image2, buffer2 = captureTestImage()

  # Count changed pixels
  logger.debug('Comparing...')
  delta = pixelDiff(buffer1, buffer2, 100, 75, threshold)


  # Save an image if pixels changed
  if delta > sensitivity:
    logger.info(now)
    logger.info('Motion detected!')
    captureRekognizeSave()

  # Swap comparison buffers
  image1 = image2
  buffer1 = buffer2

  logger.debug('Waiting for {} seconds to try again'.format(period))
  time.sleep(period)
