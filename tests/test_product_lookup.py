import unittest

from phi.upc_lookup import (
    _parse_amazon_product,
    normalize_asin,
    normalize_product_code,
    numeric_code_type,
    product_code_label,
)


class ProductCodeTests(unittest.TestCase):
    def test_normalizes_asin(self) -> None:
        self.assertEqual(normalize_asin("b08fc5l3rg"), "B08FC5L3RG")
        self.assertEqual(normalize_product_code("B08FC5L3RG"), ("B08FC5L3RG", "ASIN"))
        self.assertEqual(product_code_label("B08FC5L3RG"), "ASIN")

    def test_rejects_fnsku_as_asin(self) -> None:
        self.assertIsNone(normalize_asin("X0041EZWT1"))
        self.assertIsNone(normalize_product_code("X0041EZWT1"))
        self.assertIsNone(normalize_product_code("X001234567"))

    def test_still_normalizes_upc(self) -> None:
        self.assertEqual(normalize_product_code("711719541028"), ("711719541028", "UPC"))
        self.assertEqual(product_code_label("711719541028"), "UPC")

    def test_identifies_isbn_format(self) -> None:
        self.assertEqual(numeric_code_type("9780140328721"), "ISBN")
        self.assertEqual(numeric_code_type("9791234567896"), "ISBN")
        self.assertEqual(product_code_label("9780140328721"), "ISBN")

    def test_identifies_ean_and_gtin_formats(self) -> None:
        self.assertEqual(
            normalize_product_code("4006381333931"),
            ("4006381333931", "EAN-13"),
        )
        self.assertEqual(product_code_label("4006381333931"), "EAN-13")
        self.assertEqual(
            normalize_product_code("96385074"),
            ("96385074", "EAN-8 / UPC-E"),
        )
        self.assertEqual(numeric_code_type("10012345000017"), "GTIN-14")

    def test_parses_amazon_product_page(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:image" content="https://images.example/product.jpg">
          </head>
          <body>
            <span id="productTitle"> PlayStation 5 Console </span>
            <a id="bylineInfo"><span>Visit the PlayStation Store</span></a>
          </body>
        </html>
        """
        result = _parse_amazon_product(html, "B08FC5L3RG")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.found)
        self.assertEqual(result.upc, "B08FC5L3RG")
        self.assertEqual(result.code_type, "ASIN")
        self.assertEqual(result.name, "PlayStation 5 Console")
        self.assertEqual(result.brand, "PlayStation")
        self.assertEqual(result.image_url, "https://images.example/product.jpg")

    def test_rejects_amazon_challenge_page(self) -> None:
        self.assertIsNone(
            _parse_amazon_product(
                "<html><head><title>Amazon.com</title></head><body>Continue shopping</body></html>",
                "B08FC5L3RG",
            )
        )

    def test_parses_brand_from_product_table(self) -> None:
        html = """
        <span id="productTitle">Example Product</span>
        <table><tr><th>Brand Name</th><td>Example &amp; Co.</td></tr></table>
        """
        result = _parse_amazon_product(html, "B012345678")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.brand, "Example & Co.")


if __name__ == "__main__":
    unittest.main()
