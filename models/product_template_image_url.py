import requests
import base64
import logging
from odoo import api, SUPERUSER_ID

from odoo import api
from odoo import models, fields

_logger = logging.getLogger(__name__)

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref('product_excel_import_advanced.ir_cron_update_product_images', raise_if_not_found=False)
    if not cron:
        env['ir.cron'].create({
            'name': '产品图片异步下载',
            'model_id': env['ir.model']._get_id('product.template'),
            'state': 'code',
            'code': "model.cron_update_product_images()",
            'interval_number': 1,
            'interval_type': 'days',
            'numbercall': -1,
            'active': True,
        })

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    image_url = fields.Char('Image URL')

    @api.model
    def cron_update_product_images(self, limit=50):
        products = self.search([('image_url', '!=', False), ('image_1920', '=', False)], limit=limit)
        for product in products:
            try:
                resp = requests.get(product.image_url, timeout=30)
                if resp.status_code == 200:
                    product.image_1920 = base64.b64encode(resp.content)
                    product.image_128 = product.image_1920
                    product.image_1024 = product.image_1920
                    product.image_512 = product.image_1920
                    product.image_256 = product.image_1920
            except Exception as e:
                _logger.warning(f"Image download failed for product {product.id}: {e} : {product.image_url}")
                print(f"Image download failed for product {product.id}: {e}")
                continue
        return True
