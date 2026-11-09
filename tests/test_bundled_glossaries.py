"""Bundled glossaries stay canonical; fr-CA diverges from fr only where listed."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from glossary_store import DEFAULTS, encode, parse_document

# fr-CA Locales terms that differ from fr (keyed by first English source).
FR_CA_ONLY = {'Breakfast', 'cutoff', 'Cutoff Round', 'Dinner', 'email', 'hoodie', 'Lunch', 'puzzle',
              "Rubik's Cube", 'schedule', 'scorecard', 'upload', 'World Championship', 'world record'}


def entries(stem):
    return {e['source'][0]: e for e in parse_document((DEFAULTS / f'{stem}.json').read_text(encoding='utf-8'), stem)['entries']}


class BundledGlossaryTest(unittest.TestCase):
    def test_canonical(self):
        for path in DEFAULTS.glob('*.json'):
            with self.subTest(path.name):
                text = path.read_text(encoding='utf-8')
                self.assertEqual(encode(parse_document(text, path.stem)), text)

    def test_fr_ca_matches_fr_outside_allowlist(self):
        fr, ca = entries('fr'), entries('fr_ca')
        self.assertEqual({k: v for k, v in fr.items() if k not in FR_CA_ONLY},
                         {k: v for k, v in ca.items() if k not in FR_CA_ONLY})
        self.assertTrue(all(k in ca and fr.get(k) != ca[k] for k in FR_CA_ONLY))


if __name__ == '__main__':
    unittest.main()
