""" Vcon accessors and helpers """
import typing

transcript_accessors: typing.Dict[typing.Tuple[str, str, str], typing.Type] = {}


class TranscriptAccessor():
  """ Abstract accessor to get information from a recording transcription.
      This needs to be derived for each transcription format and then 
      registered in Vcon.transcription_accessors.
  """

  def __init__(
    self,
    transcript_dialog_dict: typing.Dict[str, typing.Any],
    transcript_analysis_dict: typing.Dict[str, typing.Any]
    ):
    self._dialog_dict = transcript_dialog_dict
    self._analysis_dict = transcript_analysis_dict


  def get_text(self) -> typing.List[typing.Dict[str, typing.Any]]:
    """
    Get text spoken by the parties in this transcription for a recording.

    Returns:
      list of dicts where each dict contains the following:
        * "party" (int) - index to the party that typed or spoke the given text
        * "text" (str) - the typed or spoken text
        * "start" (str) - the RFC3339 time stamp at which the text started/spoken/transmitted
        * "duration" (int) - optional duration over which the text was typed or spoken
    """
    raise Exception("not implemented")

