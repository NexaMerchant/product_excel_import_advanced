from odoo import models, fields

class ProductImportLog(models.Model):
    _name = "product.import.log"
    _description = "Product Import Log"

    name = fields.Char(string="Batch Name", required=True)
    total = fields.Integer("Total Rows")
    success = fields.Integer("Success Rows")
    failed = fields.Integer("Failed Rows")
    message = fields.Text("Message")
