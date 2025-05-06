import base64
import tempfile
import binascii
import requests
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import xlrd
import openpyxl

_logger = logging.getLogger(__name__)

class ProductImportWizard(models.TransientModel):
    _name = 'product.import.wizard'
    _description = 'Product Import Wizard'

    file = fields.Binary(string='Upload Excel File', required=True)
    filename = fields.Char(string='Filename')

    def action_import_products(self):
        if not self.file:
            raise UserError(_("Please upload an Excel file."))

        # decode the binary file
        try:
            file_data = base64.b64decode(self.file)
        except binascii.Error:
            raise UserError(_("Invalid file format."))

        # try opening as .xlsx or .xls
        products_data = []
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(file_data)
                tmp.flush()
                wb = openpyxl.load_workbook(tmp.name, read_only=True)
                sheet = wb.active
                for idx, row in enumerate(sheet.iter_rows(min_row=2), 2):
                    values = [cell.value for cell in row]
                    if not values or not values[0]:
                        continue  # skip empty rows
                    products_data.append((idx, values))
        except Exception:
            # fallback to .xls
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xls") as tmp:
                    tmp.write(file_data)
                    tmp.flush()
                    wb = xlrd.open_workbook(tmp.name)
                    sheet = wb.sheet_by_index(0)
                    for idx in range(1, sheet.nrows):
                        row = sheet.row(idx)
                        values = [cell.value for cell in row]
                        if not values or not values[0]:
                            continue
                        products_data.append((idx + 1, values))
            except Exception as e:
                raise UserError(_("Failed to read Excel file: %s") % str(e))

        total = len(products_data)
        success = 0
        error_msgs = []

        BATCH_SIZE = 50 # 处理批次大小

        for idx, (row_num, row) in enumerate(products_data, 1):
            print(f"Processing row {row_num}: {row}")
            print(row)
            try:
                sku = str(row[0]).strip()
                print(f"SKU: {sku}")
                if not sku:
                    raise ValueError("SKU is required.")

                # Product or create
                product = self.env['product.product'].search([('default_code', '=', sku)], limit=1)
                if not product:
                    product_tmpl = self.env['product.template'].create({
                        'name': row[3] or row[2] or sku,
                        'default_code': sku,
                        'detailed_type': 'product',
                    })
                    product = product_tmpl.product_variant_id
                else:
                    product_tmpl = product.product_tmpl_id
                    product_tmpl.name = row[2] or sku

                # # 分类匹配
                # try:
                #     category_id = int(row[4]) if row[4] else False
                #     if category_id:
                #         category = self.env['product.category'].browse(category_id)
                #         if category.exists():
                #             product_tmpl.categ_id = category
                # except Exception:
                #     pass  # 跳过错误分类

                # 图片 URL 下载
                image_url = row[6]
                print(f"Image URL: {image_url}")
                if image_url and isinstance(image_url, str) and image_url.startswith(('http://', 'https://')):
                    try:
                        response = requests.get(image_url, timeout=10)
                        print(f"Response: {response.status_code}")
                        if response.status_code == 200:
                            product_tmpl.image_1920 = base64.b64encode(response.content)
                            product_tmpl.image_1024 = base64.b64encode(response.content)
                            product_tmpl.image_512 = base64.b64encode(response.content)
                            product_tmpl.image_256 = base64.b64encode(response.content)
                            product_tmpl.image_128 = base64.b64encode(response.content)
                    except Exception as e:
                        print(f"Image download failed: {e}")
                        _logger.warning(f"[Row {row_num}] Image download failed for {image_url}: {e}")

                # 设置字段
                weight = float(row[7]) if row[7] else 0
                price = float(row[8]) if row[8] else 0
                # length = float(row[10]) if row[10] else 0
                # width = float(row[11]) if row[11] else 0
                # height = float(row[12]) if row[12] else 0

                product_tmpl.weight = weight
                product.standard_price = price
                # product_tmpl.x_length_cm = length
                # product_tmpl.x_width_cm = width
                # product_tmpl.x_height_cm = height

                # # 采购员
                # buyer_name = row[8]
                # if buyer_name:
                #     buyer = self.env['res.users'].search([('name', '=', buyer_name)], limit=1)
                #     if buyer:
                #         product_tmpl.x_buyer_id = buyer.id

                # # 开发员
                # developer_name = row[21]
                # if developer_name:
                #     developer = self.env['res.users'].search([('name', '=', developer_name)], limit=1)
                #     if developer:
                #         product_tmpl.x_developer_id = developer.id

                # save data to products_ext
                print(f"Product: {product}")
                product_ext = self.env['products_ext.products_ext'].search([('product_id', '=', product.id)], limit=1)
                print(f"Product Ext: {product_ext}")
                if not product_ext:
                    self.env['products_ext.products_ext'].create({
                        'product_id': product.id,
                        'product_url': row[13],
                        'declared_price': float(row[18]) if row[18] else 0,
                        'declared_name_cn': row[16],
                        'declared_name_en': row[15],
                    })
                else:
                    product_ext.product_url = row[13]
                    product_ext.declared_price = float(row[18]) if row[18] else 0,
                    product_ext.declared_name_cn = row[16]
                    product_ext.declared_name_en = row[15]

                success += 1
            except Exception as e:
                error_msgs.append(f"Row {row_num}: {str(e)}")
            if idx % BATCH_SIZE == 0:
                self.env.cr.commit()
                self.env.invalidate_all()

        self.env['product.import.log'].create({
            'name': self.filename,
            'total': total,
            'success': success,
            'failed': total - success,
            'message': '\n'.join(error_msgs),
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Product Import Logs'),
            'res_model': 'product.import.log',
            'view_mode': 'tree,form',
            'target': 'current',
        }
