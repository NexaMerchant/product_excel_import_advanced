import warnings
# 屏蔽 openpyxl 在读取没有默认样式的 Excel 文件时产生的特定用户警告
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl", message="Workbook contains no default style, apply openpyxl's default")
import base64
import tempfile
import binascii
import logging
import pandas as pd
import os # 用于删除临时文件
import psycopg2 

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ProductImportWizard(models.TransientModel):
    _name = 'product.import.wizard'
    _description = 'Product Import Wizard'

    file = fields.Binary(string='Upload Excel File', required=True, help="Upload an Excel file (.xls or .xlsx) for product import.")
    filename = fields.Char(string='Filename')
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
    ], string='Platform')
    default_stock_location = fields.Many2one('stock.location', string='Default Stock Location', required=True, help="Default stock location for imported products.")

    def _get_cell_value(self, row_list, col_idx, default_value=''):
        """ 安全地从列表（Excel行）中获取单元格值 """
        try:
            # pandas 读取空单元格可能为 NaN (float)，需要转换为字符串并处理
            val_raw = row_list[col_idx]
            if pd.isna(val_raw): # 处理 NaN 值
                return default_value
            val_str = str(val_raw).strip()
            # 进一步处理 pandas 自动转换的 '.0' 后缀（针对看起来像数字的字符串）
            if val_str.endswith('.0') and val_str[:-2].isdigit():
                val_str = val_str[:-2]
            return val_str if val_str else default_value
        except IndexError:
            return default_value
        except Exception as e: # 其他潜在转换错误
            _logger.warning(f"Could not process cell value at col {col_idx} (value: {row_list[col_idx] if col_idx < len(row_list) else 'OOB'}): {e}")
            return default_value

    def action_import_products(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Please upload an Excel file."))

        wizard_filename = self.filename # 将 filename 存储在局部变量中

        try:
            file_data = base64.b64decode(self.file)
        except binascii.Error:
            raise UserError(_("Invalid file format. The uploaded file could not be decoded."))

        products_data = []
        tmp_path = None
        error_msgs = []

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name
            
            df = pd.read_excel(tmp_path, header=0, engine=None, dtype=str)
            _logger.info(f"Excel columns found: {df.columns.tolist()}")

            for idx, row_series in df.iterrows():
                values = row_series.tolist()
                excel_row_num = idx + 2
                sku_val = self._get_cell_value(values, 0)
                if not sku_val:
                    msg = f"Row {excel_row_num}: SKU is empty, skipping this row."
                    error_msgs.append(msg)
                    _logger.warning(msg)
                    continue
                products_data.append((excel_row_num, values))
        except Exception as e:
            _logger.error(f"Failed to read or process Excel file: {e}", exc_info=True)
            raise UserError(_("Failed to read or process the Excel file. Error: %s") % str(e))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception as e_unlink:
                    _logger.warning(f"Could not delete temporary file {tmp_path}: {e_unlink}")
        
        if not products_data:
            _logger.info("No valid product data found in the Excel file to import.")
            if error_msgs:
                 return self._import_result(wizard_filename, 0, 0, error_msgs)
            raise UserError(_("No valid product data found in the uploaded Excel file."))

        total_to_process = len(products_data)
        successful_imports = 0
        # error_msgs 已经在上面初始化，这里不需要再次初始化

        BATCH_SIZE = 20 
        _logger.info(f"Starting product import. Total valid rows: {total_to_process}, Batch size: {BATCH_SIZE}")

        for loop_idx, (excel_row_num, row_values) in enumerate(products_data, 1):
            try:
                # _logger.debug(f"Current cursor state before processing row {excel_row_num}: {self.env.cr.closed if self.env.cr else 'No cursor'}")
                sku = self._get_cell_value(row_values, 0)
                _logger.info(f"Processing Excel row {excel_row_num}, SKU: {sku}")
                print(f"Processing Excel row {excel_row_num}, SKU: {sku}")

                if self.platform == 'dianxiaomi':
                    product_name_cn = self._get_cell_value(row_values, 2)
                    product_name_en = self._get_cell_value(row_values, 3)
                    #product_name = product_name_en or product_name_cn or sku
                    product_name = product_name_en + product_name_cn + sku
                    # 图片处理
                    image_url = self._get_cell_value(row_values, 6)
                    # 报关数据处理
                    product_url_ext = self._get_cell_value(row_values, 13)
                    decl_name_en_ext = self._get_cell_value(row_values, 15)
                    decl_name_cn_ext = self._get_cell_value(row_values, 16)
                    decl_price_str_ext = self._get_cell_value(row_values, 18, '0.0')
                elif self.platform == 'mabangerp':
                    product_name_cn = self._get_cell_value(row_values, 2)
                    product_name_en = self._get_cell_value(row_values, 3)
                    # product name include en and cn and sku
                    product_name = product_name_en + product_name_cn + sku

                    #product_name = product_name_en or product_name_cn or sku

                    # 图片处理
                    image_url = self._get_cell_value(row_values, 12) 
                    # 报关数据处理
                    product_url_ext = self._get_cell_value(row_values, 11)
                    decl_name_en_ext = self._get_cell_value(row_values, 4)
                    decl_name_cn_ext = self._get_cell_value(row_values, 5)
                    decl_price_str_ext = self._get_cell_value(row_values, 6, '0.0')
                else: # 默认处理方式 店小蜜
                    product_name_cn = self._get_cell_value(row_values, 2)
                    product_name_en = self._get_cell_value(row_values, 3)
                    product_name = product_name_en or product_name_cn or sku
                    image_url = self._get_cell_value(row_values, 6)
                    product_url_ext = self._get_cell_value(row_values, 13)
                    decl_name_en_ext = self._get_cell_value(row_values, 15)
                    decl_name_cn_ext = self._get_cell_value(row_values, 16)
                    decl_price_str_ext = self._get_cell_value(row_values, 18, '0.0')
                
                # 核心改动点：在可能导致游标关闭的 commit 操作之后，这里的 search 需要特别小心
                # 尝试在 search 前确保游标是活动的，或者让 Odoo ORM 自己处理
                # 如果之前的 commit 导致游标关闭，Odoo 在执行新的SQL时应该会尝试获取新游标
                product = self.env['product.product'].search([('default_code', '=', sku)], limit=1)
                product_tmpl = None

                if not product:
                    product_tmpl_vals = {
                        'name': product_name,
                        'default_code': sku,
                        'detailed_type': 'product',
                    }
                    if(self.default_stock_location):
                        product_tmpl_vals['property_stock_inventory'] = self.default_stock_location.id
                    product_tmpl = self.env['product.template'].create(product_tmpl_vals)
                    product = product_tmpl.product_variant_ids[:1]
                    if not product:
                        msg = f"Row {excel_row_num} (SKU: {sku}): Failed to create product variant."
                        error_msgs.append(msg)
                        _logger.error(msg)
                        continue
                    _logger.info(f"Row {excel_row_num}: Created product '{product.name}' (ID: {product.id}) for SKU {sku}")
                else:
                    product_tmpl = product.product_tmpl_id
                    if product_tmpl.name != product_name:
                        product_tmpl.write({'name': product_name})
                        _logger.info(f"Row {excel_row_num}: Updated name for SKU {sku} to '{product_name}'")
                    # 更新库存位置
                    if self.default_stock_location and product_tmpl.property_stock_inventory != self.default_stock_location:
                        product_tmpl.property_stock_inventory = self.default_stock_location
                
                
                if image_url and image_url.startswith(('http://', 'https://')):
                    if product_tmpl.image_url != image_url:
                        product_tmpl.image_url = image_url
                        _logger.info(f"Row {excel_row_num}: Set image_url for SKU {sku} to {image_url}")

                weight_str = self._get_cell_value(row_values, 7, '0.0')
                cost_price_str = self._get_cell_value(row_values, 8, '0.0')
                
                try:
                    weight_val = float(weight_str)
                    if product_tmpl.weight != weight_val: product_tmpl.weight = weight_val
                except ValueError:
                    msg = f"Row {excel_row_num} (SKU: {sku}): Invalid weight value '{weight_str}'."
                    error_msgs.append(msg)
                    _logger.warning(msg)
                
                try:
                    cost_price_val = float(cost_price_str)
                    if product.standard_price != cost_price_val: product.standard_price = cost_price_val
                except ValueError:
                    msg = f"Row {excel_row_num} (SKU: {sku}): Invalid cost price value '{cost_price_str}'."
                    error_msgs.append(msg)
                    _logger.warning(msg)

                if 'products_ext.products_ext' in self.env:
                    
                    try:
                        decl_price_val_ext = float(decl_price_str_ext)
                    except ValueError:
                        msg = f"Row {excel_row_num} (SKU: {sku}): Invalid declared price '{decl_price_str_ext}'. Using 0.0."
                        error_msgs.append(msg)
                        _logger.warning(msg)
                        decl_price_val_ext = 0.0
                    
                    ext_record = self.env['products_ext.products_ext'].search([('product_id', '=', product.id)], limit=1)
                    ext_vals = {
                        'product_url': product_url_ext,
                        'declared_name_en': decl_name_en_ext,
                        'declared_name_cn': decl_name_cn_ext,
                        'declared_price': decl_price_val_ext,
                    }
                    if not ext_record:
                        ext_vals['product_id'] = product.id
                        self.env['products_ext.products_ext'].create(ext_vals)
                    else:
                        ext_record.write(ext_vals)
                else:
                    _logger.debug("Model 'products_ext.products_ext' not found. Skipping.")

                successful_imports += 1
            except psycopg2.Error as e_db_row: # Catch psycopg2 errors specifically
                msg = f"Row {excel_row_num} (SKU: {self._get_cell_value(row_values, 0, 'N/A')}): Database error: {str(e_db_row)}"
                error_msgs.append(msg)
                _logger.error(msg, exc_info=True)
                # If a db error occurs, the transaction might be aborted, and cursor closed.
                # It's safer to stop and report.
                error_msgs.append("CRITICAL: Database error occurred. Import stopped to prevent further issues.")
                return self._import_result(wizard_filename, total_to_process, successful_imports, error_msgs)
            except Exception as e_row:
                msg = f"Row {excel_row_num} (SKU: {self._get_cell_value(row_values, 0, 'N/A')}): Processing error: {str(e_row)}"
                error_msgs.append(msg)
                _logger.error(msg, exc_info=True)
                continue

            if loop_idx % BATCH_SIZE == 0:
                _logger.info(f"Attempting to commit batch at loop_idx {loop_idx} (Excel row {excel_row_num})")
                try:
                    self.env.cr.commit() # Commit the transaction
                    self.env.invalidate_all() # Invalidate cache
                    # After commit, the cursor is closed. Odoo should handle getting a new one for the next operation.
                    # No need to explicitly re-wrap self.env with self.with_env here for basic operations.
                    # If issues persist, this is an area to revisit.
                    _logger.info(f"Committed batch. Last processed Excel row: {excel_row_num}")
                except psycopg2.Error as e_commit_db: # Catch psycopg2 errors specifically during commit
                    _logger.error(f"CRITICAL: Database error during commit at batch {loop_idx} (Excel row {excel_row_num}): {e_commit_db}", exc_info=True)
                    error_msgs.append(f"CRITICAL: DB commit failed at batch {loop_idx}. Import stopped. Error: {e_commit_db}")
                    return self._import_result(wizard_filename, total_to_process, successful_imports, error_msgs)
                except Exception as e_commit:
                    _logger.error(f"CRITICAL: Error committing transaction at batch {loop_idx} (Excel row {excel_row_num}): {e_commit}", exc_info=True)
                    error_msgs.append(f"CRITICAL: Commit failed at batch {loop_idx}. Import stopped. Error: {e_commit}")
                    return self._import_result(wizard_filename, total_to_process, successful_imports, error_msgs)
        
        # Final commit for any remaining records
        # Check if there are records processed since the last batch commit OR if total is less than BATCH_SIZE
        if total_to_process > 0 and (loop_idx % BATCH_SIZE != 0 or total_to_process < BATCH_SIZE) :
             _logger.info(f"Attempting final commit for remaining records. Loop index: {loop_idx}, Total processed: {successful_imports}")
             try:
                self.env.cr.commit()
                self.env.invalidate_all()
                _logger.info("Final commit successful.")
             except psycopg2.Error as e_final_db:
                _logger.error(f"CRITICAL: Database error during final commit: {e_final_db}", exc_info=True)
                error_msgs.append(f"CRITICAL: DB error during final commit. Error: {e_final_db}")
             except Exception as e_final_commit:
                _logger.error(f"CRITICAL: Error during final commit: {e_final_commit}", exc_info=True)
                error_msgs.append(f"CRITICAL: Error during final commit. Error: {e_final_commit}")

        _logger.info(f"Product import finished. Total rows: {total_to_process}, Successful: {successful_imports}, Errors/Skipped: {len(error_msgs)}")
        return self._import_result(wizard_filename,total_to_process, successful_imports, error_msgs)


    def _import_result(self, import_filename, total_rows, success_count, error_list):
        try:
            log_message = '\n'.join(error_list)
            self.env['product.import.log'].create({
                'name': import_filename or f"Product Import @ {fields.Datetime.now(self)}",
                'total': total_rows,
                'success': success_count,
                'failed': total_rows - success_count,
                'platform': self.platform,
                'default_stock_location': self.default_stock_location.id if self.default_stock_location else False,
                'import_file': self.file,
                'message': log_message,
            })
            _logger.info("Import log record created.")
        except psycopg2.Error as log_db_e: # Catch specific DB error for logging
             _logger.error(f"CRITICAL: Database error while creating import log: {log_db_e}", exc_info=True)
        except Exception as log_e:
            _logger.error(f"CRITICAL: Failed to create import log record: {log_e}", exc_info=True)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Product Import Logs'),
            'res_model': 'product.import.log',
            'view_mode': 'tree,form',
            'target': 'current',
        }
