import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
import string
import sys
import logging

def send(messageQueue, subject, recipient, text=None, htmlFile=None,
    textFile=None, templateArgs=None):
    messageQueue.put('email', json.dumps(
        dict(subject=subject, recipient=recipient, htmlFile=htmlFile,
            text=text, textFile=textFile, templateArgs=templateArgs)))


class MessageHandler(object):
    smtpArgs = None
     
    def __init__(self, smtpArgs):
        self.smtpArgs = smtpArgs


    def __call__(self, message):
        message = json.loads(message) 

        # Get parameters from the message
        recipient = message.get('recipient')
        subject = message.get('subject')
        text = message.get('text')
        htmlFile = message.get('htmlFile')
        textFile = message.get('textFile')
        templateArgs = message.get('templateArgs')

        # Ignore the message if required args aren't given
        if recipient is None or subject is None:
            logging.log(logging.WARNING, 'Ignoring email message because it '
                    + 'does not have a recipient and/or subject.') 
            return

        if text is None and htmlFile is None and textFile is None:
            logging.log(logging.WARNING, 'Ignoring email message because it '
                    + 'does not have a body.') 
            return

        # Assemble message
        emailMsg = text is not None and MIMEText(text) \
                or MIMEMultipart('alternative')
        emailMsg['Subject'] = message['subject']
        emailMsg['From'] = self.smtpArgs['email']
        emailMsg['To'] = message['recipient']

        if textFile is not None:
            # Load text version of the message from the given file
            text = open(message['textFile']).read()

            # Perform template substitution, if any
            if templateArgs is not None:
                text = string.Template(text).substitute(templateArgs)

            # Record the MIME type - text/plain
            part1 = MIMEText(text, 'plain')

            # Attach part into message container
            emailMsg.attach(part1)

        if htmlFile is not None:
            # Load html version of the message from the given file
            html = open(message['htmlFile']).read()

            # Perform template substitution, if any
            if templateArgs is not None:
                html = string.Template(html).substitute(templateArgs)

            # Record the MIME type - text/html
            part2 = MIMEText(html, 'html')

            # According to RFC 2046, the last part of a multipart message, in 
            # this case the HTML message, is best and preferred.
            emailMsg.attach(part2)

        # Login to our email provider
        s = smtplib.SMTP(host=self.smtpArgs['host'], 
                port=self.smtpArgs['port'])
        try:
            x = s.starttls()
            s.login(self.smtpArgs['email'], self.smtpArgs['password'])

            # Send the message
            s.sendmail(self.smtpArgs['email'], 
                    message['recipient'], emailMsg.as_string())
        finally:
            s.quit()
