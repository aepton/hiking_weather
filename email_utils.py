import boto3
import os

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

EMAIL_FROM_ADDRESS = os.environ.get('HIKING_EMAIL_FROM_ADDRESS', '')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')

def send_email(
  from_address=EMAIL_FROM_ADDRESS,
  to_addresses=[],
  subject='',
  body=''):

  connection = boto3.client('ses', region_name=AWS_REGION)

  for address in to_addresses:
    message = MIMEMultipart('alternative')
    message['Subject'] = subject
    message['From'] = from_address
    message['To'] = address

    part_text = MIMEText(body, 'plain')
    message.attach(part_text)

    part_html = MIMEText(body, 'html')
    message.attach(part_html)

    print('Emailing {}'.format(address))
    try:
      connection.send_raw_email(
        RawMessage={
          'Data': message.as_string()
        },
        Source=message['From'],
        Destinations=[message['To']])
    except Exception as e:
      print('Error {} sending email: {}'.format(e, message))
      print('To: {}'.format(address))