# vCon Interop 1 Testing Assets
The following assets are to be used for constructing vCons using your software or application for the Stage 1 Tests.
Public HTTP URLs are provided which may be used in constructing externally referenced dialog content.

## SMS Exchange Assets
The following files are intended to be an SMS text exchange between the two parties:
+ Alice tel:+12345678901
+ Bob tel:+12345678902

SMS messages:
+ Message 1 From: Alice Date: 2025-04-18T13:48:25.265-04:00 [text file](https://raw.githubusercontent.com/py-vcon/py-vcon/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/SMS1_Alice_%2B12345678901.txt)
+ Message 2 From: Bob Date: 2025-04-18T13:49:26.265-04:00 [text file](https://raw.githubusercontent.com/py-vcon/py-vcon/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/SMS2_Bob_%2B12345678902.txt)
+ Message 3 From: Alice Date: 2025-04-18T13:50:27.265-04:00 [text file](https://raw.githubusercontent.com/py-vcon/py-vcon/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/SMS3_Alice_%2B12345678901.txt)
+ Message 4 From: Bob Date: 2025-04-18T13:51:28.265-04:00 [text file](https://raw.githubusercontent.com/py-vcon/py-vcon/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/SMS4_Bob_%2B12345678902.txt)

## Email Message Thread
Use the following raw SMTP messages from a single email thread to construct a single vCon:
+ SMTP Message 1: [raw smtp file](https://raw.githubusercontent.com/py-vcon/py-vcon/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/email1.eml)
+ SMTP Message 2: [raw smtp file](https://raw.githubusercontent.com/py-vcon/py-vcon/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/email2.eml)
+ SMTP Message 3: [raw smtp file](https://raw.githubusercontent.com/py-vcon/py-vcon/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/email3.eml)

## Audio Call recording
Use the following recording files and party information to construct a vCon for each of the audio formats that your vCon software supports:  
Call From: Alice to: Bob  Date: 2025-04-18T14:04:28.658-04:00 public http links: [wav](https://github.com/py-vcon/py-vcon/raw/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/call.wav), [mp3](https://github.com/py-vcon/py-vcon/raw/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/call.mp3), [ma4](https://github.com/py-vcon/py-vcon/raw/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/call.m4a)  
Note: you can use the above URLs to construct vCons with externally referenced audio dialogs.

## Video Call Recording
Use the following video recording, party and dialog information to construct a vCon:  
Video recording Originator: Dan Participant: Jeff Start: 2025-04-18T15:59:31.123-04:00 public http link: [url](https://github.com/py-vcon/py-vcon/raw/refs/heads/main/vcon_interop_public/vcon_interop_1_assets/video.mp4)  
Note: you can use the above URLs to construct vCons with externally referenced video dialogs.

## Certificates and keys
Use the following certifcates and keys when signing, verifying, encrypting and decrypting your vCons:  
* Use this [Private Key]() to sign or decrypt

Key Chain (public keys/certs.):  
* Use this [Top level authority]() to verify that the cert below is trusted
* [Mid level issuer]()
* Use this [cert]() to verify or encrypt
