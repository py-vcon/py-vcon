# vcon command line tool

## Introduction
The vcon command provides the ability to create and modify JSON format vCons.  The command works like a filter or pipe with an input and output, which is often a JSON format vcon in either the unsigned, signed or encrypted form.  Command operators are specified to modify the input and create the output.  By defulat the input is assumed on stdin and output is provided on stdout.  The -n, -i and -o options override the input and output source.

## Usage:

```
vcon [I/O Options] [Operations]

```

## I/O Options

The **-n**, **-i**, **-g** options are mutually exclusive.

&nbsp;&nbsp;&nbsp;&nbsp;**-n** - create a new vCon and do not read input from file or stdin.

&nbsp;&nbsp;&nbsp;&nbsp;**-i FILE** - read a vCon from the given file name instead of the default stdin.

&nbsp;&nbsp;&nbsp;&nbsp;**-g HOST PORT UUID** - do a HTTP get to read in a vCon from the given HOST, PORT having the given UUID instead of the default stdin.  Assumes the URL: http://HOST:PORT/vcon/UUID


&nbsp;&nbsp;&nbsp;&nbsp;**-o FILE** - write the result of the command operation to the given file name instead of the default stdout

&nbsp;&nbsp;&nbsp;&nbsp;**-p HOST PORT** - HTTP post the resulting output vCon to the given HOST and PORT.  This option does not change the stdout or effect of the -o option.

&nbsp;&nbsp;&nbsp;&nbsp;**-r FILTER_NAME MODULE_NAME CLASS_NAME INIT_OPTIONS** - Load the MODULE_NAME and register the CLASS_NAME as a vcon filter plugin using the FILTER_NAME.  The INIT_OPTIONS is a JSON dict containing option parameters input to the initialization of the filter plugin.  If the default INIT_OPTIONS is desired, use: "{}".  Any existing filter registered as FILTER_NAME will be replaced.  Note, this registration only exists for the life of this vcon command.  Generally this is used in conjunction with the **filter** option defined below.

## Command Operation

&nbsp;&nbsp;&nbsp;&nbsp;**add in-meet VIDEO_FILE** - add inline recording dialog, text dialogs for chat and attachments from a Google Meet recording.  The VIDEO_FILE is a mp4 video recording created by Google Meet for a recorded meeting.  The chat file name is implied with the same meeting name and date prefix as the VIDEO_FILE.  Text dialog(s) will be created for the chat messages found in the chat file.

&nbsp;&nbsp;&nbsp;&nbsp;**add in-zoom DIR** - add inline recording dialog, text dialogs for chat and attachments from a Zoom recording.  The DIR is a directory created by Zoom for a recorded meeting that contains the **recording.conf**, **.mp4** audio or video recording and optionally a **chat.txt** file.  Any other files in the directory are considered attachments exchanged during the meeting and will be added as inline attachment objects to to the vCon.

&nbsp;&nbsp;&nbsp;&nbsp;**add in-email FILE** - read a raw SMTP/email message from the given file name and add it to the vCon dialog Object array, add the parties found in the From, To and CC fields to the vCon parties Object array, if the input vCon does not already have a subject set, read the Subject header from the SMTP message and set the vCon subject parameter.  The dialog Object parameters: parties, start, mimetype, encoding and body are all filled in based upon the information in the SMTP message.

&nbsp;&nbsp;&nbsp;&nbsp;**add in-recording FILE DATE PARTIES** - add a inline dialog to the input vCon containing the given recording file name, use the given date as the start time for the recording and the given parties as the participants in the recording.  The date must be the epoch time (seconds since 1970) as an integer or double; or a string RFC2822 or RFC3339 format date. The parties must be a string representing either an integer, an integer array, or an array of integers or integer arrays in JSON format, representing the parties contributing to the media in the corresponding channel.


&nbsp;&nbsp;&nbsp;&nbsp;**add ex-recording FILE DATE PARTIES URL** - add a dialog to the input vCon referencing the given recording file name, use the given date as the start time for the recording and the given parties as the participants in the recording, where the recording is stored at the given HTTPS url.  The date must be the epoch time (seconds since 1970) as an integer or double; or a string RFC2822 or RFC3339 format date. The parties must be a string representing either an integer, an integer array, or an array of integers or integer arrays in JSON format, representing the parties contributing to the media in the corresponding channel.

&nbsp;&nbsp;&nbsp;&nbsp;**filter FILTER_NAME [-fo FILTER_OPTIONS]** run the FILTER_NAME filter plugin on the input vcon.  Currently the only builtin filter plugin is **transcribe**.  Othere comming soon.  FILTER_OPTIONS is a quoted curly bracket surrounded string defining a dict as input options for the filter (e.g. "{foo='bar', verbose=True, number=6}" )



&nbsp;&nbsp;&nbsp;&nbsp;**sign KEY [CERT ...]** sign the input vCon using the given private key, attaching the given list of certificates as the cert chain in the x5c parameter.  The output is a vCon in the sgined form (JOSE JWS JSON).

&nbsp;&nbsp;&nbsp;&nbsp;**extract dialog INDEX** extract the body from the inline dialog Object at the given index.  The result is provided on stdout.  The output may be ascii or binary.  No vCon JSON is provide as output.

&nbsp;&nbsp;&nbsp;&nbsp;**verify CERT** verify the signature of the input signed vCon and verify that the certificate in the given file name is in the key chain contained in the x5c or x5u certificate chain contained in the input vCon

&nbsp;&nbsp;&nbsp;&nbsp;**encrypt CERT** encrypt the input signed vCon using the certificate in the given file name

&nbsp;&nbsp;&nbsp;&nbsp;**decrypt KEY CERT** decrypt the input encrypted vCon using the private key and certificate in the given file names.

## Examples

Create a new empty vCon with just the vcon and uuid parameters set:

    vcon -n

Read in a vcon from a file named **a.vcon** and add an inline dialog for the recording file **recording.wav** with the recording start time where the single channel recording captures the parties identified in the parties Object array at index 0 and 1:

    vcon -i a.vcon add in-recording recording.wav 2022-06-21T13:53:26-04:00 "[0,1]"

Read in a vcon from a file named **b.vcon** and add an externally referenced dialog for the recording file: ** agent_simple.wav** with the recording start time, single channel recording for parties 0 and 1:

    vcon -i b.vcon add ex-recording ../../examples/agent_sample.wav "2023-03-06T20:07:43+00:00" "[0,1]"  https://github.com/vcon-dev/vcon/blob/main/examples/agent_sample.wav?raw=true

Read in a vcon from a file named **a.vcon** and sign it with the private key in the file **my.key** which is in the key chain contained in the files **c.crt**, **b.crt** and **a.crt**:

    vcon -i a.vcon sign my.key c.crt b.crt a.crt

Read in the signed vCon from the file named **signed.vcon** and output the verified vCon in unsigned form, verifying the key chain in the x5c parameter has the certificate contained in the file named **auth.crt** as a certificate of authority:

    vcon -i signed.vcon verify auth.crt

Note: piping the output to the jq command can be useful for extracting specific parameters or creating a pretty print formated JSON output.  For example, the follwing will pretty print the vcon output:

    vcon -n | jw '.'

Output:

    {
      "vcon": "0.0.1",
      "parties": [],
      "dialog": [],
      "analysis": [],
      "attachments": [],
      "uuid": "01838260-d37e-87b3-973a-91e26eb8001b"
    }

To obtain the value of the uuid parameter from the output vCon:

    vcon -n | jq '.uuid'

To set the name parameter of the first party in an existing Vcon:

    vcon -i myvcon.vcon | jq '. | .parties[0] += {name: "Foo Bar"}'

To create a new vcon, add a recording of parties 0 and 1, starting at the current time and pipe that into another vcon command to transcribe the recording:

    vcon -n add in-recording ~/dev/vcon/examples/agent_sample.wav  "`date --rfc-3339=seconds`"  "[0,1]" | vcon filter transcribe

To create a new vCon and add dialogs and attachments from a Zoom meeting recording:

    vcon -n add in-zoom zoom_recording_directory/

To create a new vCon and add dialogs and attachments from a Google Meet recording:

    vcon -n add in-meet 'tests/google_meet/test meeting (2023-09-06 20:27 GMT-4) (18af10d0)' 

