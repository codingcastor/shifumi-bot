from enum import Enum

class Gesture(Enum):
    ROCK = "ROCK"
    PAPER = "PAPER"
    SCISSORS = "SCISSORS"

    @property
    def emoji(self):
        """Return the emoji representation of the gesture"""
        return {
            self.ROCK: ":rock:",
            self.PAPER: ":leaves:",
            self.SCISSORS: ":scissors:"
        }[self]

    @classmethod
    def from_input(cls, text):
        """Convert various input formats to a Gesture"""
        text = text.upper().strip()
        mapping = {
            # Rock variations
            "ROCK": cls.ROCK,
            ":ROCK:": cls.ROCK,
            "PIERRE": cls.ROCK,
            "CAILLOU": cls.ROCK,
            "CAILLOUX": cls.ROCK,
            ":CAILLOU:": cls.ROCK,
            # Paper variations
            "PAPER": cls.PAPER,
            "FEUILLE": cls.PAPER,
            "FEUILLES": cls.PAPER,
            ":LEAVES:": cls.PAPER,
            ":FEUILLE:": cls.PAPER,
            # Scissors variations
            "SCISSORS": cls.SCISSORS,
            "CISEAUX": cls.SCISSORS,
            ":SCISSORS:": cls.SCISSORS,
            ":CISEAUX:": cls.SCISSORS,
        }
        if text not in mapping:
            raise ValueError(f"Invalid gesture: {text}")
        return mapping[text]

