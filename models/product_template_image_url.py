import requests
import base64
import logging
from odoo import api, SUPERUSER_ID, models, fields, _
# from odoo import api # 重复导入，已合并
# from odoo import models, fields # 重复导入，已合并

_logger = logging.getLogger(__name__)

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # 确保 cron 的 external ID 与 XML 文件中的 ID 一致
    # 如果你在 XML 文件中定义了 cron，例如 <record id="ir_cron_product_image_download" model="ir.cron">
    # 那么这里应该是 env.ref('product_excel_import_advanced.ir_cron_product_image_download', raise_if_not_found=False)
    # 如果你的模块名是 product_excel_import_advanced，并且 XML 文件中 cron 的 id 是 ir_cron_update_product_images
    cron_xml_id = 'product_excel_import_advanced.ir_cron_update_product_images' # 假设这是 XML 中定义的 ID
    cron = env.ref(cron_xml_id, raise_if_not_found=False)
    if not cron:
        # 如果 XML 中没有定义，或者想通过代码创建/确保存在
        model_product_template_id = env['ir.model']._get_id('product.template')
        existing_cron = env['ir.cron'].search([
            ('model_id', '=', model_product_template_id),
            ('code', '=', 'model.cron_update_product_images()')
        ], limit=1)
        if not existing_cron:
            env['ir.cron'].create({
                'name': 'Product Images: Async Download', # 更具描述性的名称
                'model_id': model_product_template_id,
                'state': 'code',
                'code': "model.cron_update_product_images()",
                'interval_number': 1, # 例如每小时执行一次
                'interval_type': 'hours',
                'numbercall': -1, # 无限次调用
                'active': True,
                'user_id': SUPERUSER_ID, # 确保以超级用户执行
                'doall': False, # 如果上次执行错过了，不要立即重新运行所有错过的
            })
            _logger.info(f"Cron job '{cron_xml_id}' created for product image download.")
        else:
            _logger.info(f"Cron job for product image download already exists with ID {existing_cron.id}.")
    else:
        _logger.info(f"Cron job '{cron_xml_id}' for product image download found.")


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    image_url = fields.Char('Image URL', help="URL from where the product image can be downloaded.")

    @api.model
    def cron_update_product_images(self, limit_per_run=20, download_timeout=30, commit_batch_size=10):
        """
        Cron job to download images for products that have an image_url but no image_1920.
        :param limit_per_run: Max number of products to process in one run of this cron.
        :param download_timeout: Timeout in seconds for the image download request.
        :param commit_batch_size: Number of successful image updates before a database commit.
        """
        _logger.info(f"Starting cron_update_product_images: limit_per_run={limit_per_run}, commit_batch_size={commit_batch_size}")
        # Search for products that have an image_url and no image_1920 (or image_1920 is an empty byte string)
        # Using SUPERUSER_ID to bypass access rights if necessary for a system cron
        Product = self.with_user(SUPERUSER_ID).env['product.template']
        products_to_process = Product.search([
            ('image_url', '!=', False),
            ('image_url', 'not like', 'localhost'), # Optionally skip localhost URLs if they are problematic
            ('image_url', 'not like', '127.0.0.1'),
            '|',
            ('image_1920', '=', False),
            ('image_1920', '=', b'') # Check for empty byte string as well
        ], limit=limit_per_run)

        if not products_to_process:
            _logger.info("No products found requiring image download in this run.")
            return True

        _logger.info(f"Found {len(products_to_process)} products to attempt image download.")
        processed_count = 0
        success_count = 0

        for product in products_to_process:
            processed_count += 1
            image_content = None
            try:
                _logger.info(f"Attempting to download image for product ID {product.id} (SKU: {product.default_code}) from URL: {product.image_url}")
                response = requests.get(product.image_url, timeout=download_timeout, stream=True)
                response.raise_for_status() # Will raise an HTTPError for bad responses (4xx or 5xx)
                
                # Check content type if necessary, e.g., 'image/jpeg', 'image/png'
                # content_type = response.headers.get('content-type')
                # if not content_type or not content_type.startswith('image/'):
                #     _logger.warning(f"URL {product.image_url} for product ID {product.id} did not return an image content-type: {content_type}")
                #     continue

                image_content = response.content # Read the content
                if not image_content:
                    _logger.warning(f"Downloaded image content is empty for product ID {product.id} from URL: {product.image_url}")
                    continue

            except requests.exceptions.Timeout:
                _logger.warning(f"Timeout downloading image for product ID {product.id} from URL: {product.image_url}")
                continue
            except requests.exceptions.RequestException as e:
                _logger.warning(f"Failed to download image for product ID {product.id} from URL {product.image_url}: {e}")
                continue
            except Exception as e:
                _logger.error(f"Unexpected error downloading image for product ID {product.id} from URL {product.image_url}: {e}", exc_info=True)
                continue

            if image_content:
                try:
                    # Storing the main image, Odoo will auto-generate other sizes
                    product.write({'image_1920': base64.b64encode(image_content)})
                    _logger.info(f"Successfully downloaded and saved image for product ID {product.id} (SKU: {product.default_code}).")
                    success_count += 1

                    # Commit in batches
                    if success_count % commit_batch_size == 0:
                        self.env.cr.commit()
                        # Re-initialize self.env to ensure it's valid after commit
                        # self = self.with_env(api.Environment(self.env.cr, self.env.uid, self.env.context)) # Not strictly needed if not re-using self for search/write
                        _logger.info(f"Committed batch of {commit_batch_size} image updates. Total successful so far: {success_count}")
                except Exception as e_write:
                    _logger.error(f"Failed to write image to product ID {product.id} (SKU: {product.default_code}): {e_write}", exc_info=True)
                    self.env.cr.rollback() # Rollback the failed write for this product
                    continue # Continue to the next product

        # Final commit for any remaining successful downloads not yet committed
        if success_count > 0 and success_count % commit_batch_size != 0:
            try:
                self.env.cr.commit()
                _logger.info(f"Committed final batch of image updates. Total successful in this run: {success_count}")
            except Exception as e_final_commit:
                _logger.error(f"Failed during final commit for image updates: {e_final_commit}", exc_info=True)
                self.env.cr.rollback()


        _logger.info(f"Finished cron_update_product_images: Processed {processed_count} products, successfully updated {success_count} images.")
        return True
