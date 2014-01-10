import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
import string
from contextlib import closing
import functools

import MySQLdb

def send(messageQueue, subject, recipient, htmlFile=None,
    textFile=None, templateArgs=None):
    messageQueue.put('email', json.dumps(
        dict(subject=subject, recipient=recipient, htmlFile=htmlFile,
            textFile=textFile, templateArgs=templateArgs)))


class MessageHandler(object):
    smtpArgs = None
     
    def __init__(self, smtpArgs):
        self.smtpArgs = smtpArgs


    def __call__(self, message):
        cursor = None
        try:
            message = json.loads(message) 

            # Ignore the message if required args aren't given
            if 'recipient' not in message \
                    or 'htmlFile' not in message \
                    or 'textFile' not in message \
                    or 'subject' not in message \
                    or 'templateArgs' not in message:
                sys.stderr.write('Ignoring email message because it is not '
                    + 'complete.\n')
                return
            
            # Assemble MIME multipart message
            emailMsg = MIMEMultipart('alternative')
            emailMsg['Subject'] = message['subject']
            emailMsg['From'] = self.smtpArgs['email']
            emailMsg['To'] = message['recipient']

            # Load html and text versions of the message from the given files
            text = open(message['textFile']).read()
            html = open(message['htmlFile']).read()

            # Perform template substitution, if any
            text = string.Template(text).substitute(message['templateArgs'])
            html = string.Template(html).substitute(message['templateArgs'])

            # Record the MIME types of both parts - text/plain and text/html
            part1 = MIMEText(text, 'plain')
            part2 = MIMEText(html, 'html')

            # Attach parts into message container.
            # According to RFC 2046, the last part of a multipart message, in 
            # this case the HTML message, is best and preferred.
            emailMsg.attach(part1)
            emailMsg.attach(part2)

            # Login to our email provider
            s = smtplib.SMTP(host=self.smtpArgs['host'], 
                    port=self.smtpArgs['port'])
            x = s.starttls()
            s.login(self.smtpArgs['email'], self.smtpArgs['password'])

            # Send the message
            s.sendmail(self.smtpArgs['email'], 
                    message['recipient'], emailMsg.as_string())
            s.quit()

        finally:
            if cursor is not None:
                cursor.close()
