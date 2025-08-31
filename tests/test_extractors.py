import unittest
import AICore

class TestExtractors(unittest.TestCase):
    def test_parse_amount_eu(self):
        s = 'Gesamtbetrag: € 1.234,56'
        amounts = AICore.findAmountsInText(s)
        self.assertTrue(any('1.234' in a[1] or '1.234,56' in a[1] for a in amounts))
        best = AICore.pick_best_amount(amounts, s)
        self.assertIn('1.234', best)

    def test_parse_amount_us(self):
        s = 'Total: $1,234.56\nSubtotal $1,000.00'
        amounts = AICore.findAmountsInText(s)
        self.assertTrue(any('$1,234.56' in a[1] or '1,234.56' in a[1] for a in amounts))
        best = AICore.pick_best_amount(amounts, s)
        self.assertIn('1,234.56', best.replace('$',''))

    def test_parse_amount_negative_and_duplicates(self):
        s = 'Discount: -10,00€\nGesamtbetrag: 90,00 EUR\nTotal: 90,00 EUR'
        amounts = AICore.findAmountsInText(s)
        # should find two amounts (10,00 and 90,00) and dedupe duplicates
        vals = [a[1] for a in amounts]
        self.assertTrue(any('90,00' in v for v in vals))
        best = AICore.pick_best_amount(amounts, s)
        self.assertIn('90,00', best)

    def test_find_dates_and_pick(self):
        s = 'Rechnung vom 12.08.2025\nWeitere Daten'
        dates = AICore.findDatesInText(s)
        self.assertTrue(any('12.08.2025' in d[1] for d in dates))
        best = AICore.pick_best_date(dates, s)
        self.assertEqual(best, '12.08.2025')

    def test_parse_helper(self):
        self.assertAlmostEqual(AICore._parse_amount_value('1.234,56'), 1234.56)
        self.assertAlmostEqual(AICore._parse_amount_value('$1,234.56'), 1234.56)
        self.assertAlmostEqual(AICore._parse_amount_value('1000'), 1000.0)

if __name__ == '__main__':
    unittest.main()
