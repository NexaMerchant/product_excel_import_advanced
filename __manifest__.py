{
    "name": "Product Excel Import Advanced",
    "summary": "Import product data from Excel with SKU match, image, and logs",
    "version": "1.0",
    "depends": ["base", "product","stock","products_batch"],
    "author": "Steve Liu",
    "category": "Product",
    "data": [
        "security/ir.model.access.csv",
        "views/product_import_wizard_view.xml",
        "views/product_import_log_view.xml",
    ],
    "installable": True,
    "application": True,
}
