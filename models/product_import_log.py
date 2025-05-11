from odoo import models, fields

class ProductImportLog(models.Model):
    _name = "product.import.log"
    _description = "Product Import Log"

    name = fields.Char(string="Batch Name", required=True)
    platform = fields.Selection([
        ('dianxiaomi', '店小秘'),
        ('mabangerp', '马帮ERP'),
        ('odoo', 'Odoo'),
        ('shopify', 'Shopify'),
        ('woocommerce', 'WooCommerce'),
        ('magento', 'Magento'),
        ('ebay', 'eBay'),
        ('amazon', 'Amazon'),
        ('wish', 'Wish'),
        ('aliexpress', 'AliExpress'),
        ('lazada', 'Lazada'),
        ('shopee', 'Shopee'),
        ('jd', '京东'),
        ('taobao', '淘宝'),
        ('tmall', '天猫'),
        ('pinduoduo', '拼多多'),
        ('suning', '苏宁易购'),
        ('dangdang', '当当网'),
        ('yihaodian', '一号店'),
        ('vipshop', '唯品会'),
        ('tianmao', '天猫国际'),
        ('kaola', '考拉海购'),
        ], string="Platform", required=True, help="Select the platform import template for product import.")
    default_stock_location = fields.Many2one('stock.location', string="Default Stock Location", required=True)
    import_file = fields.Binary("Import File", required=True)
    total = fields.Integer("Total Rows")
    success = fields.Integer("Success Rows")
    failed = fields.Integer("Failed Rows")
    message = fields.Text("Message")
