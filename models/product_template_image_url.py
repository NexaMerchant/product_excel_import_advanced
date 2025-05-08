import requests
import base64
import logging
import socket
from urllib.parse import urlparse
from odoo import api, SUPERUSER_ID, models, fields, _

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    image_url = fields.Char('Image URL', help="URL from where the product image can be downloaded.")
    image_download_fail_count = fields.Integer(
        string='Image Download Fail Count',
        default=0,
        help="Tracks the number of consecutive failed attempts to download the image."
    )
    image_download_failed = fields.Boolean(
        string='Image Download Failed',
        default=False,
        help="Indicates if the image download has failed 3 times and needs manual intervention."
    )

    @api.model
    def cron_update_product_images(self, limit_per_run=20, download_timeout=60, commit_batch_size=10):
        _logger.info(f"Starting cron_update_product_images: limit_per_run={limit_per_run}, commit_batch_size={commit_batch_size}")
        Product = self.with_user(SUPERUSER_ID).env['product.template']
        products_to_process = Product.search([
            ('image_url', '!=', False),
            ('image_url', 'not like', 'localhost'),
            ('image_url', 'not like', '127.0.0.1'),
            '|',
            ('image_1920', '=', False),
            ('image_1920', '=', b''),
            ('image_download_failed', '=', False)
        ], limit=limit_per_run)

        if not products_to_process:
            _logger.info("No products found requiring image download in this run.")
            return True

        _logger.info(f"Found {len(products_to_process)} products to attempt image download.")
        processed_count = 0
        success_count = 0

        image_url_cache = {}

        for product in products_to_process:
            processed_count += 1
            image_content = None

            # 验证 URL 是否有效
            def is_valid_url(url):
                parsed = urlparse(url)
                return bool(parsed.netloc) and bool(parsed.scheme)

            if not is_valid_url(product.image_url):
                _logger.warning(f"Invalid URL for product ID {product.id}: {product.image_url}")
                product.image_download_fail_count += 1
                if product.image_download_fail_count >= 3:
                    product.image_download_failed = True
                continue

            # 1. 优先查本地缓存
            if product.image_url in image_url_cache:
                image_content = image_url_cache[product.image_url]
                _logger.info(f"Reusing cached image for product ID {product.id} (SKU: {product.default_code}) from URL: {product.image_url}")
            else:
                # 2. 查数据库是否有其它产品已下载该图片
                other = Product.search([
                    ('image_url', '=', product.image_url),
                    ('image_1920', '!=', False),
                    ('id', '!=', product.id)
                ], limit=1)
                if other and other.image_1920:
                    image_content = base64.b64decode(other.image_1920)
                    image_url_cache[product.image_url] = image_content
                    _logger.info(f"Reusing DB image for product ID {product.id} (SKU: {product.default_code}) from URL: {product.image_url}")
                else:
                    # 3. 需要下载
                    try:
                        _logger.info(f"Attempting to download image for product ID {product.id} (SKU: {product.default_code}) from URL: {product.image_url}")
                        response = requests.get(product.image_url, timeout=download_timeout, stream=True)
                        response.raise_for_status()
                        # 限制最大图片为10MB
                        max_size = 10 * 1024 * 1024
                        image_chunks = []
                        total_size = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                image_chunks.append(chunk)
                                total_size += len(chunk)
                                if total_size > max_size:
                                    _logger.warning(f"Image too large for product ID {product.id}: {total_size} bytes, aborting.")
                                    raise ValueError("Image too large")
                        image_content = b"".join(image_chunks)
                        if not image_content:
                            _logger.warning(f"Downloaded image content is empty for product ID {product.id} from URL: {product.image_url}")
                            raise ValueError("Empty image content")
                        image_url_cache[product.image_url] = image_content
                        response.close()
                    except (requests.exceptions.Timeout, requests.exceptions.RequestException, socket.error, ValueError) as e:
                        _logger.warning(f"Failed to download image for product ID {product.id} from URL {product.image_url}: {e}")
                        product.image_download_fail_count += 1
                        if product.image_download_fail_count >= 3:
                            product.image_download_failed = True
                            _logger.warning(f"Product ID {product.id} (SKU: {product.default_code}) marked as failed after 3 unsuccessful attempts.")
                        try:
                            if 'response' in locals():
                                response.close()
                        except Exception:
                            pass
                        continue
                    except Exception as e:
                        _logger.error(f"Unexpected error downloading image for product ID {product.id} from URL {product.image_url}: {e}", exc_info=True)
                        try:
                            if 'response' in locals():
                                response.close()
                        except Exception:
                            pass
                        continue

            if image_content:
                try:
                    product.write({
                        'image_1920': base64.b64encode(image_content),
                        'image_download_fail_count': 0,
                        'image_download_failed': False
                    })
                    _logger.info(f"Successfully downloaded and saved image for product ID {product.id} (SKU: {product.default_code}).")
                    success_count += 1

                    if success_count % commit_batch_size == 0:
                        self.env.cr.commit()
                        _logger.info(f"Committed batch of {commit_batch_size} image updates. Total successful so far: {success_count}")
                except Exception as e_write:
                    _logger.error(f"Failed to write image to product ID {product.id} (SKU: {product.default_code}): {e_write}", exc_info=True)
                    self.env.cr.rollback()
                    continue

        if success_count > 0 and success_count % commit_batch_size != 0:
            try:
                self.env.cr.commit()
                _logger.info(f"Committed final batch of image updates. Total successful in this run: {success_count}")
            except Exception as e_final_commit:
                _logger.error(f"Failed during final commit for image updates: {e_final_commit}", exc_info=True)
                self.env.cr.rollback()

        _logger.info(f"Finished cron_update_product_images: Processed {processed_count} products, successfully updated {success_count} images.")
        return True