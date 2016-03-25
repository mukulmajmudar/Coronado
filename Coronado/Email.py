import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import string
import logging

from .Worker import WorkHandler
from .Exceptions import MissingArgument

logger = logging.getLogger(__name__)

class SendEmail(WorkHandler):

    def __call__(self):
        message = self.request.body

        # Get parameters from the message
        recipient = message.get('recipient')
        subject = message.get('subject')
        text = message.get('text')
        htmlFile = message.get('htmlFile')
        textFile = message.get('textFile')
        templateArgs = message.get('templateArgs')

        # Ignore the message if required args aren't given
        if recipient is None or subject is None:
            raise MissingArgument('Missing recipient and/or subject')

        if text is None and htmlFile is None and textFile is None:
            raise MissingArgument('Missing body')

        smtpArgs = self._context['smtp']

        # Assemble message
        emailMsg = text is not None and MIMEText(text) \
                or MIMEMultipart('alternative')
        emailMsg['Subject'] = message['subject']
        emailMsg['From'] = message.get('sender', smtpArgs['email'])
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
        s = smtplib.SMTP(host=smtpArgs['host'],
                port=smtpArgs['port'])
        try:
            s.starttls()
            s.login(smtpArgs['email'], smtpArgs['password'])

            # Send the message
            logger.info('Sending email to %s', message['recipient'])
            s.send_message(emailMsg)
        finally:
            s.quit()
