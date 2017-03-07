TACOS
======

What?
-----
TACOS (There's A Cat On the Sundeck) is a python script for detecting cats (and as a recent addition, other animals) on my sundeck.
It does this by regularly taking pictures, uploading them to Amazon S3 and running object detection on them using Amazon Rekognition.
If it finds a Cat (or an animal), it notifies those subscribed via Amazon SNS, with links to the picture in which it was detected, and
some additional info if it was an animal.

But why?
---------

Why not?




Running yourself
--------------------

To run this for yourself, you need:

+ A Raspberry Pi
+ An internet connection
+ A Raspberry Pi camera
+ An Amazon AWS account

If you have all these, set up an S3 bucket and a SNS topic, and note these in the variables in the script.
Then make sure you have an IAM user that can access SNS and the bucket (you can give the user full access, but I gave the user access only to it's particular key in the bucket).
Make sure that the IAM user also has permission to use Rekognition, specifically the "rekognition:detectLabels" permission (or again, full access to rekognition).
If you have all these set up, fill in the details in the script, make sure that the credentials for the IAM user are accessible, and start it up!

Troubleshooting
------------------

+ The camera doesn't work.

  Make sure that you've enabled the camera interface in raspi-config

+ The detection gives me errors

  Make sure that boto is able to access your IAM user, and make sure that user has permissions for S3, Rekognition and SNS.
