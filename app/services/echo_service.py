class EchoService:
    """
    Business logic for the echo example.

    The simplest possible service: no dal or libs objects to wrap, just a
    place to add validation or logging around what would otherwise be a
    trivial passthrough.
    """

    def echo(self, message: str) -> str:
        """
        Return the message unchanged.

        :param message: message to echo back.
        :return: same message.
        """
        return message
