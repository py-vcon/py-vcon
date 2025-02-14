# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.

import typing
import email.message
import pydantic
import aiosmtplib
import py_vcon_server.processor

logger = py_vcon_server.logging_utils.init_logger(__name__)

class SendEmailInitOptions(py_vcon_server.processor.VconProcessorInitOptions):
  """
  SendEmailInitOptions is passed to the send_email processor when it is initialized.
  SendEmailInitOptions extends VconProcessorInitOptions, but does not add any new fields.
  """

class SendEmailOptions(py_vcon_server.processor.VconProcessorOptions):
  """
  SendEmailOptions provides the SMTP headers and message data required to send
  an SMTP email message.  SendEmailOptions is passed to the send_email processor.
  """
  smtp_host: str = pydantic.Field(
      title = "SMTP server host to connect to, to send email messages",
      description = "Should be set if authentication is required.  If unset or emtpy string, the server name in the To address is used",
      default = ""
    )

  smtp_port: int = pydantic.Field(
      title = "SMTP server port to connect to, to send email messages",
      description = "Should be set if authentication is required.",
      default = 0
    )

  smtp_user: str = pydantic.Field(
      title = "authentication user ID to used to login to SMTP server",
      default = ""
    )

  smtp_password: str = pydantic.Field(
      title = "authentication password to used to login to SMTP server",
      default = ""
    )

  use_tls: bool = pydantic.Field(
      title = "connect to SMTP server using TLS",
      default = False
    )

  from_address: str = pydantic.Field(
      title = "email address for sender",
      description = "string containing From address to send message from.  Address must be of the form: 'user@host' or 'First Last \<user@host\>'",
      default = ""
    )

  to: typing.List[str] = pydantic.Field(
      title = "list of To email addresses",
      description = "list of strings containing To address(es) to send message to.  Address must be of the form: 'user@host' or 'First Last \<user@host\>'",
      default = []
    )

  cc: typing.List[str] = pydantic.Field(
      title = "list of Cc email addresses",
      description = "list of strings containing Cc address(es) to copy/send message to.  Address must be of the form: 'user@host' or 'First Last \<user@host\>'",
      default = []
    )

  bcc: typing.List[str] = pydantic.Field(
      title = "list of Bcc email addresses",
      description = "list of strings containing Bcc address(es) to blind copy/send message to.  Address must be of the form: 'user@host' or 'First Last \<user@host\>'",
      default = []
    )

  subject: str = pydantic.Field(
      title = "subject field for the email message to be sent",
      default = ""
    )

  text_body: str = pydantic.Field(
      title = "main text body of the email message to be sent",
      default = ""
    )

  client_hostname: str = pydantic.Field(
      title = "FQHN provided for SMTP client when connecting to SMTP server.",
      default = ""
    )


class SendEmail(py_vcon_server.processor.VconProcessor):
  """ Processor to set VconProcessorIO parameters from options """

  def __init__(
    self,
    init_options: SendEmailInitOptions
    ):

    super().__init__(
      "VconProcessor to send email message",
      "used to send SMTP messages using content from vCon or VconProcessorIP parameters.",
      "0.0.1",
      init_options,
      SendEmailOptions,
      False # modifies a Vcon
      )


  async def process(self,
    processor_input: py_vcon_server.processor.VconProcessorIO,
    options: SendEmailOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
    """
    Set the VconProcessorIO parameters from the input options parameters.  Does not modify the vCons.
    """

    email_message = email.message.EmailMessage()
    email_message.set_content(options.text_body)
    if(len(options.from_address)):
      email_message["From"] = options.from_address
    if(len(options.subject)):
      email_message["Subject"] = options.subject
    if(len(options.to)):
      email_message["To"] = ",".join(options.to)
    if(len(options.cc)):
      email_message["Cc"] = ",".join(options.cc)
    if(len(options.bcc)):
      email_message["Bcc"] = ",".join(options.bcc)
    # TODO add support for attachements and multipart MIME

    if(len(options.smtp_user) or
       len(options.smtp_password) or
       options.use_tls):
      use_tls = True
    else:
      use_tls = False

    if(options.smtp_host is not None and
       len(options.smtp_host)):
      host = options.smtp_host
    else:
      host = None

    if(options.smtp_port > 0):
      port = options.smtp_port
    else:
      port = None

    if(options.smtp_user is not None and
       len(options.smtp_user)):
      smtp_user = options.smtp_user
    else:
      smtp_user = None

    if(options.smtp_password is not None and
       len(options.smtp_password)):
      password = options.smtp_password
    else:
      password = None

    if(options.client_hostname is not None and
       len(options.client_hostname)):
      local_hostname = options.client_hostname
    else:
      local_hostname = None

    logger.debug("sending message via SMTP server: {} port: {} using TLS: {}".format(host, port, use_tls))
    await aiosmtplib.send(
        email_message,
        hostname = host,
        port = port,
        username = smtp_user,
        password = password,
        use_tls = use_tls,
        local_hostname = local_hostname
      )

    return(processor_input)

