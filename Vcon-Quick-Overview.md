
# vCons in Five Minutes
## Summary
A vCon (Virtual Conversation Container) is a standard container for storing and managing conversational data (such as transcripts and multimedia files) generated in business communication, particularly in customer-facing organizations. It contains metadata, dialog, analysis and attachments portions, which include information such as participant identification, conversation contents, sentiment analysis, context documents, and integrity checking information. vCons can be used to ease service integration, help with data management and privacy, and serve as input for communication analysis and machine learning tools. They are designed to be digital assets that are versioned and signed for data integrity and provenance. The use of vCons helps lower the cost and speed deployment of analysis tools and eases customer analysis across different product lines.

## Object Format
The vCon JSON object is a JSON representation of a virtual conversation, used to enable the interchange of conversation data between applications and lower layers of the network stack. The vCon has three forms: unsigned, signed, and encrypted. The unsigned form of vCon has a single top-level JSON object and is necessary for cases where the vCon is partially constructed or changes while the conversation is in progress. The signed and encrypted forms of vCon include the same top-level object. The vCon JSON object includes several keys and values such as: vcon (version of the JSON format), uuid (unique identifier for the vCon), subject (topic of the conversation), and redacted (reference to a less redacted version of the vCon).

## Parties
The Parties Object in JSON vCon is used to store information about the participants in a conversation. Each party involved in a conversation is represented as a separate object in the parties array. The Parties Object can include the following parameters:
* id: a unique identifier for the party.
* type: the type of party, such as "person", "group", or "system".
* name: the name of the party.
* address: the communication address or identifier for the party, such as a phone number or email address.
* display: a display name or nickname for the party.
* picture: a reference to an image file that represents the party, such as a profile picture.
* role: the role of the party in the conversation, such as "initiator" or "recipient".
* note: a note or description of the party.

These parameters are used to provide a complete picture of each party involved in the conversation, which can be useful for analysis and other purposes. 

Single channel recordings should have a parties value of the form UnsignedInt or UnsignedInt[], where the integer value or array of integer values are the indices to the Party Object(s) in the parties array that contributed to the mix for the single channel recording. The index for the Party Object should be included even if the indicated party was silent the entire piece of dialog.

Multi-channel recordings must have a parties value that is an array of the same size as the number of channels in the recording. The values in that array are either an integer or an array of integers which are the indices to the parties that contributed to the mix for the associated channel of the recording. The index for Party Objects should be included even if the party was silent the entire conversation.

## Dialog
The Dialog object in a vCon is used to store information about text, audio, or video captured from a conversation. It contains the following parameters:

* type (mandatory): either "recording" or "text"
* start (mandatory): date and time for the beginning of the captured piece of dialog
* duration (optional): duration in seconds of the referenced or included piece of dialog
* parties (mandatory): parties which generated the text or recording
* mimetype (optional for external references): media type of the piece of dialog
* filename (optional): name of the file originally containing the dialog
* body (for inline included dialog) or url (for externally referenced dialog)

Additionally, for inline included dialog, there is an encoding parameter, and for externally referenced dialog, there are alg and signature parameters.Analysis Object

## Analysis
The Analysis Object is used to store information about an analysis data related to the conversation. The analysis data can be included inline in the JSON file, or it can be an external file.
Properties
* type: This parameter is used to label the semantic type of analysis data. It is a string value and its value should be one of the following: "summary", "transcript", "translation", "sentiment", "tts".
* dialog: This parameter is used to indicate which Dialog Objects the analysis was based upon. The value of the dialog parameter is the index to the dialog or array of indices to dialogs in the dialog array to which this analysis object corresponds.
* mimetype: The media type for the included or referenced analysis file is provided in this parameter.
* filename: The filename parameter can be used to preserve the name of the file which originally contained the analysis data.
* vendor: There may not be a media type defined for the file format containing the analysis data. The vendor parameter allows the product name of the software that produced the analysis to be saved.
* schema: The schema parameter allows the data format, schema, or configuration used to generate the analysis to be saved.
* body: The body parameter is used for inline included analysis. It contains the string representation of the analysis data.
* encoding: The encoding parameter is used for inline included analysis. It contains the string representation of the encoding used for the analysis data.
* url: The url parameter is used for externally referenced analysis. It contains the URL pointing to the location of the analysis data.
* alg: The alg parameter is used for externally referenced analysis. It contains the string representation of the algorithm used to generate the signature.
* signature: The signature parameter is used for externally referenced analysis. It contains the signature for the analysis data.

## Attachment

The Attachment Object is used to include or reference ancillary documents related to the conversation. Any file type can be included or referenced here.
Properties

* type or purpose: The type or purpose property can be used to specify the semantic type or purpose of the attached file.
* party: The party parameter is used to indicate which Party Object the attachment is related to. The value of the party parameter is the index to the party in the party array to which this attachment object corresponds.
