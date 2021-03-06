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
# The bucket the pictures are uploaded to.
# Make sure you have permissions to Put, Delete and Get.
bucket = 'iot-mpg-is'
# The prefix of the pictures in the bucket.
path = 'nullid/picam-'
# The max brightness of the pictures, if brightness is changed based on
# time of day
maxb = 60
# The pictures per second period.
period = 0.10
# The SNS topic to send notifications to if anything is detected
topic = 'arn:aws:sns:eu-west-1:384599271648:iot-nullid-taco'
# How much a pixel has to change to be noticed
threshold = 20
# Whether to enable dynamic sensitivity changes
dynamicSensitivity = False
# Configuration for the dynamic senstivity
initial_sensitivity = 250
sensitivity_step = 50
max_sensitivity = 5000
min_sensitivity = 250
# How many changed pixels to count as 'motion'
sensitivity = initial_sensitivity
# How much to rotate the camera, one of 0, 90, 180, 270.
rotation = 270
# Labels deemed interesting, if any of these are detected, a notification is
# sent.
interests = ['Cat', 'Animal','Face', 'Person']
# The resoulution of the pictures uploaded to S3 and rekognized.
resolution = (1000, 1000)
# The resolution used for motion detection. Note: do no set this too high,
# since we actually want pixels that are close by each other to be unified.
# A TODO is to use 16x16 macro blocks, and detect change between them, as
# the per pixel metric is bad for higher resolutions.
motion_res = (100, 100)



logger = logging.getLogger(__name__)
now = datetime.datetime.now()
logging.basicConfig(filename='taco-log-{}-{}-{}'.format(now.year,
                                                        now.month,
                                                        now.day),
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
from twython import Twython
import auth

camera = picamera.PiCamera()
s3 = boto3.client('s3')
rek = boto3.client('rekognition')
sns = boto3.client('sns')

logger.info('Initialization done!')


# Capture a small test image (for motion detection)
def captureTestImage():
  imageData = BytesIO()
  # what format is appropriate? does it matter?
  camera.capture(imageData,
                 format='jpeg',
                 resize=(motion_res[0],motion_res[1]))
  imageData.seek(0)
  image = Image.open(imageData)
  pixels = image.load()
  imageData.close()
  return image, pixels


# The number of pixels that differ more than threshold between pixel
# access arrays im1 and im2 of width w and height h is greater than sensitivity
def pixelDiff(im1, im2, w, h, threshold):
  changedPixels = 0
  for x in range(w):
    for y in range(h):
       # Just check green channel as it's the highest quality channel
       pixdiff = abs(im1[x, y][1] - im2[x, y][1])
       if pixdiff > threshold:
         changedPixels += 1
  return changedPixels




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

  res = rek.detect_labels(Image={'S3Object': {'Bucket': bucket,
                                              'Name': objname}},
                          MaxLabels=10)

  labels = res['Labels']
  lks = map(lambda label: (label['Name'], label['Confidence']), labels)
  LabelMap = dict(lks)
  logger.info(LabelMap)
  link = 'https://s3-eu-west-1.amazonaws.com/{}/{}'.format(bucket, objname)


  def letKnow(type):
    logger.info('{} sighted! Notifying!'.format(type))
    s3.put_object_acl(ACL='public-read', Bucket=bucket, Key=objname)
    msg = 'TACOS Alert! {} detected in {}! See it at {}. The labels were {}'\
           .format(type, objname, link, json.dumps(LabelMap))
    sns.publish(TopicArn=topic, Message=msg)
    if type == 'Cat':
      tweet('TACOS detected a kitty with a confidence of {}! See it at {}.'\
            .format(LabelMap['Cat'], link))

  interestsInMap = list(filter(lambda x: x in LabelMap, interests))
  if interestsInMap:
    letKnow(interestsInMap[0])
  else:
    logger.info('Nothing interesting detected... :(')
    logger.info('Deleting non-interesting picture')
    s3.delete_object(Bucket=bucket, Key=objname)
  return LabelMap

if rotation:
  camera.rotation = rotation

logger.info("Resolution is set to {}".format(camera.resolution))
camera.brightness = 50
camera.resolution = resolution
camera.capture('/tmp/picam.jpg')
# Camera warmup time
time.sleep(2)
image1, buffer1 = captureTestImage()

def setCameraBrightness():
  '''Sets the camera brightness depending on the time of day.
  Returns a Boolean describing whether the brightness changed.'''
  return False # Don't worry about brightness for now.

  now = datetime.datetime.now()

  oldbrightness = camera.brightness
  camera.brightness = int(min(maxb, abs((now.hour - 12) / 24) * maxb + 50))
  return (camera.brightness - oldbrightness) != 0

logger.info('Starting!')

def detectAndSetExposure():
  logger.info('Detecting what exposure to use:')
  labelMap = captureRekognizeSave()
  oldmode = camera.exposure_mode
  mode = None
  if 'Night' in labelMap:
    mode = 'night'
  elif 'Snow' in labelMap:
    mode = 'snow'
  else:
    mode = 'auto'
  camera.exposure_mode = mode
  logger.info('Set exposure mode to {}, giving time to adjust...'\
              .format(mode))
  time.sleep(2)
  return oldmode == mode

def tweet(msg):
  try:
    return Twython(auth.consumer_key,
                   auth.consumer_secret,
                   auth.access_token,
                   auth.access_token_secret).update_status(status=msg)
  except Exception as e:
    logger.exception(e)



now = datetime.datetime.now()
lastCheckedExposureMinute = now.minute
lastSensitivityDrop = now.minute
detectAndSetExposure()
logger.info("Resolution is set to {}".format(camera.resolution))


while True:
  try:
    now = datetime.datetime.now()
    exposureChanged = False
    if now.minute % 15 == 0 and now.minute != lastCheckedExposureMinute:
      exposureChanged = detectAndSetExposure()
      lastCheckedExposureMinute = now.minute

    if (dynamicSensitivity
        and now.minute % 5 == 0
        and now.minute != lastSensitivityDrop):
      logger.info("Periodically lowering sensitivity!")
      sensitivity -= sensitivity_step
      sensitivity = max(sensitivity, min_sensitivity)
      logger.info("Sensitivity is now {}".format(sensitivity))
      lastSensitivityDrop = now.minute

    brightnessChanged = setCameraBrightness() # Make it more bright at night
    if brightnessChanged or exposureChanged:
      # If the brightness changed, the comparison is useless, since most of
      # the pixels will have changed.
      logger.info('Brightness changed to {}, taking another one!'\
                  .format(camera.brightness))
      image1, buffer1 = captureTestImage()
      time.sleep(period)

    # Capture comparison image
    logger.debug('Taking picture for comparison...')
    image2, buffer2 = captureTestImage()

    # Count changed pixels
    logger.debug('Comparing...')
    delta = pixelDiff(buffer1, buffer2,
                      motion_res[0], motion_res[1], threshold)

    # Save an image if pixels changed
    if delta > sensitivity:
      logger.info(now)
      logger.info('Motion detected! {} pixels changed'.format(delta))
      LabelMap = captureRekognizeSave()
      interestsInMap = list(filter(lambda x: x in LabelMap, interests))
      if dynamicSensitivity and not interestsInMap:
        logger.info("Nothing detected, raising sensitivity!")
        sensitivity += sensitivity_step
        sensitivity = min(sensitivity, max_sensitivity)
        logger.info("Sensitivity is now {}".format(sensitivity))

    # Swap comparison buffers
    image1 = image2
    buffer1 = buffer2

    logger.debug('Waiting for {} seconds to try again'.format(period))
    time.sleep(period)
  except Exception as e:
    logger.info("An exception occurred!") 
    logger.exception(e)
