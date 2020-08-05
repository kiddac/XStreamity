from Components.Sources.Source import Source


class StaticText(Source):
    def __init__(self, text="", filter=lambda x: x):
        Source.__init__(self)
        self.__text = text
        self.filter = filter

    def handleCommand(self, cmd):
        self.text = self.filter(cmd)

    def getText(self):
        return self.__text

    def setText(self, text):
        self.__text = text
        self.changed((self.CHANGED_ALL,))

    text = property(getText, setText)

    def getBoolean(self):
        return bool(self.__text)

    boolean = property(getBoolean)
