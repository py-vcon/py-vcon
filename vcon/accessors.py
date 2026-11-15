# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Vcon accessors and helpers """
import datetime
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
        * "parties" (Union[int, list[int]]) - index or list of indices to the party(s) that typed or spoke the given text
        * "text" (str) - the typed or spoken text
        * "start" (str) - the RFC3339 time stamp at which the text started/spoken/transmitted
        * "duration" (int) - optional duration over which the text was typed or spoken
    """
    raise Exception("not implemented")


  def channel_contributors(
    self,
    channel : int,
    num_channels : int,
    start : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float, None] = None
    ) -> typing.Union[int, typing.List[int], None]:
    """
    Get the party(s) heard on a channel of the recording from start for duration.

    This default uses only the Dialog Object parties: the whole parties value
    for a single channel recording, else the element for the channel, None if
    there is none.  Vcon.get_dialog_text replaces it on the accessors it builds
    with one which also applies the channel-contributors Event Objects (see
    Vcon.get_channel_contributors).

    Parameters:
      channel (int): index of the channel, 0 is the first
      num_channels (int): number of channels in the recording
      start (str, int, float, datetime.datetime): time from which the party(s) are wanted
      duration (int, float): seconds from start, None for the party(s) at start

    Returns:
      party index, list of party indices or None
    """
    parties = self._dialog_dict.get("parties", None)
    if(num_channels == 1):
      return(parties)
    if(isinstance(parties, list) and channel < len(parties)):
      return(parties[channel])
    return(None)

