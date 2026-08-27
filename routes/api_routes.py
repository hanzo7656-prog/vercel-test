# routes/api_routes.py
# ============================================================
# روت‌های API - پیش‌بینی، مدل، تسک‌ها، تست
# ============================================================

import json
import time
import secrets
from datetime import datetime, timedelta
from flask import jsonify, request, redirect, send_from_directory

from auth_manager import get_auth, require_auth, get_current_user_from_request
from numeric_analyzer import NumericAnalyzer
from command_system import CommandSystem


def register_api_routes(app, system):
    """ثبت روت‌های API در Flask app"""
    
    # ============================================================
    # ۱. روت‌های پیش‌بینی
    # ============================================================
    
    @app.route('/predict', methods=['GET'])
    def predict():
        """
        پیش‌بینی الگو با Background Task (سریع - بدون Timeout)
        """
        coin = request.args.get('coin', 'bitcoin')
        period = request.args.get('period', '24h')
        
        valid_periods = ["24h", "1w", "1m", "3m", "6m"]
        if period not in valid_periods:
            return jsonify({
                "error": "InvalidPeriod",
                "message": f"بازه زمانی باید یکی از {valid_periods} باشد",
                "provided": period
            }), 400
        
        result = system.predict_sync(coin, period)  # استفاده از predict_sync
        return jsonify(result), 200

    @app.route('/predict-sync', methods=['GET'])
    def predict_sync():
        """پیش‌بینی الگو به صورت همگام (ممکنه Timeout بخوره)"""
        coin = request.args.get('coin', 'bitcoin')
        period = request.args.get('period', '24h')
        
        valid_periods = ["24h", "1w", "1m", "3m", "6m"]
        if period not in valid_periods:
            return jsonify({
                "error": "InvalidPeriod",
                "message": f"بازه زمانی باید یکی از {valid_periods} باشد",
                "provided": period
            }), 400
        
        result = system.predict_sync(coin, period)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

    # ============================================================
    # ۲. روت‌های تست API
    # ============================================================
    
    @app.route('/test-api', methods=['GET'])
    def test_api():
        """تست ارتباط با API و نمایش داده‌های خام"""
        coin = request.args.get('coin', 'bitcoin')
        period = request.args.get('period', '24h')
        data_type = request.args.get('type', 'chart')
        
        valid_types = ['chart', 'coin', 'fear_greed', 'btc_dominance', 
                       'market', 'coins', 'news', 'status', 'credits']
        if data_type not in valid_types:
            return jsonify({
                "error": "InvalidType",
                "message": f"نوع داده باید یکی از {valid_types} باشد",
                "provided": data_type
            }), 400
        
        try:
            if data_type == 'chart':
                data = system.api.get_chart(coin, period)
                if data and "error" not in data:
                    return jsonify({
                        "success": True,
                        "count": len(data),
                        "sample": data[:5] if len(data) > 5 else data,
                        "first_point": data[0] if data else None,
                        "last_point": data[-1] if data else None,
                    })
                return jsonify({"success": False, "error": data.get("message", "خطا") if data else "داده‌ای دریافت نشد"}), 400
                
            elif data_type == 'coin':
                data = system.api.get_coin(coin)
                if data and "error" not in data:
                    return jsonify({"success": True, "data": data})
                return jsonify({"success": False, "error": data.get("message", "خطا") if data else "داده‌ای دریافت نشد"}), 400
                
            elif data_type == 'fear_greed':
                data = system.api.get_fear_greed(use_cache=False)
                if data and "error" not in data:
                    return jsonify({"success": True, "data": data})
                return jsonify({"success": False, "error": data.get("message", "خطا") if data else "داده‌ای دریافت نشد"}), 400
                
            elif data_type == 'credits':
                data = system.api.get_credits()
                if data and "error" not in data:
                    return jsonify({
                        "success": True,
                        "data": {
                            "totalCredits": data.get('totalCredits'),
                            "usedCredits": data.get('usedCredits'),
                            "remainingCredits": data.get('remainingCredits'),
                            "subscription": data.get('subscription', 'free')
                        }
                    })
                return jsonify({"success": False, "error": data.get("message", "خطا") if data else "داده‌ای دریافت نشد"}), 400
                
            elif data_type == 'status':
                data = system.api.get_status()
                return jsonify({"success": True, "data": data})
                
            else:
                return jsonify({"success": False, "error": f"نوع {data_type} پشتیبانی نمی‌شود"}), 400
                
        except Exception as e:
            import logging
            logging.error(f"Error in test-api: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ============================================================
    # ۳. روت‌های مدل و آموزش
    # ============================================================
    
    @app.route('/model/status', methods=['GET'])
    def model_status():
        """دریافت وضعیت مدل و آموزش"""
        try:
            status = system.trainer.get_stats()
            return jsonify(status)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/model/train', methods=['POST'])
    def model_train():
        """اجرای دستی آموزش"""
        try:
            period = request.args.get('period', '1m')
            result = system.trainer.train_model(period=period)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/model/start', methods=['POST'])
    def model_start():
        """شروع آموزش خودکار"""
        try:
            interval = int(request.args.get('interval', 6))
            period = request.args.get('period', '1m')
            result = system.trainer.start_auto_train(interval_hours=interval, period=period)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/model/stop', methods=['POST'])
    def model_stop():
        """متوقف کردن آموزش خودکار"""
        try:
            result = system.trainer.stop_auto_train()
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/model/history', methods=['GET'])
    def model_history():
        """دریافت سابقه آموزش با فیلتر دوره"""
        try:
            period = request.args.get('period', None)
            history = system.trainer.get_training_history(period)
            return jsonify({
                "success": True,
                "data": history,
                "count": len(history),
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/model/clear-logs', methods=['POST'])
    def model_clear_logs():
        """پاک کردن لاگ‌های آموزش"""
        try:
            system.trainer.clear_logs()
            return jsonify({"success": True, "message": "لاگ‌ها پاک شدند"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/model/versions', methods=['GET'])
    def model_versions():
        """دریافت تاریخچه نسخه‌های مدل"""
        try:
            history = system.model_manager.get_version_history(limit=20)
            return jsonify({
                "success": True,
                "data": history,
                "count": len(history)
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/model/version/<version>', methods=['GET'])
    def model_version_detail(version):
        """دریافت اطلاعات یک نسخه خاص"""
        try:
            model = system.model_manager.get_model_by_version(version)
            if model:
                return jsonify({
                    "success": True,
                    "version": version,
                    "loaded": True
                })
            return jsonify({"success": False, "message": "مدل یافت نشد"}), 404
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/model/current', methods=['GET'])
    def model_current():
        """دریافت وضعیت مدل جاری"""
        try:
            stats = system.model_manager.get_stats()
            trainer_stats = system.trainer.get_stats() if hasattr(system, 'trainer') else {}
            
            return jsonify({
                "success": True,
                "data": {
                    "loaded": stats.get('loaded', False),
                    "version": stats.get('version', 'N/A'),
                    "accuracy": trainer_stats.get('stats', {}).get('last_score'),
                    "total_trainings": trainer_stats.get('stats', {}).get('total_trainings', 0),
                    "mode": trainer_stats.get('stats', {}).get('mode', 'DEMO')
                }
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # ============================================================
    # ۴. روت‌های تحلیلگر (Command System)
    # ============================================================
    
    @app.route('/api/command', methods=['POST'])
    def process_command():
        """پردازش دستور متنی کاربر"""
        try:
            data = request.json
            command = data.get('command', '').strip()
            
            if not command:
                return jsonify({"success": False, "error": "دستور وارد نشده"}), 400
            
            # دریافت اطلاعات کاربر
            user_id = None
            session_id = request.cookies.get('session_id')
            if session_id:
                auth_manager = get_auth()
                session = auth_manager.verify_session(session_id)
                if session:
                    user_id = session.get('username')
            
            # ایجاد CommandSystem
            numeric_analyzer = NumericAnalyzer(system.api, system.model_manager)
            command_system = CommandSystem(numeric_analyzer)
            
            # پردازش دستور
            response = command_system.process_command(command, user_id)
            
            return jsonify({
                "success": True,
                "response": response,
                "command": command,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            import logging
            logging.error(f"Error in process_command: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/analyze/<coin>', methods=['GET'])
    def analyze_coin(coin):
        """تحلیل عددی یک ارز با تمام شاخص‌ها"""
        period = request.args.get('period', '24h')
        try:
            numeric_analyzer = NumericAnalyzer(system.api, system.model_manager)
            analysis = numeric_analyzer.analyze_coin(coin, period)
            return jsonify({"success": True, "data": analysis})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # ============================================================
    # ۵. روت‌های دیتابیس
    # ============================================================
    
    @app.route('/health/database', methods=['GET'])
    def health_database():
        """بررسی سلامت همه دیتابیس‌ها"""
        from database import health_check
        return jsonify({
            "success": True,
            "data": health_check(),
            "timestamp": datetime.now().isoformat()
        })

    @app.route('/api/db/postgresql/tables', methods=['GET'])
    def get_postgresql_tables():
        """دریافت لیست جدول‌های PostgreSQL"""
        from database import get_primary
        
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({"success": False, "error": "دیتابیس متصل نیست"}), 503
        
        try:
            tables = db.execute("""
                SELECT 
                    table_name,
                    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = t.table_name) as row_count
                FROM information_schema.tables t
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            for table in tables:
                size_result = db.execute(f"""
                    SELECT pg_total_relation_size('{table['table_name']}') / 1024 / 1024 as size_mb
                """)
                table['size_mb'] = size_result[0]['size_mb'] if size_result else 0
            
            return jsonify({
                "success": True,
                "data": tables
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/db/redis/keys', methods=['GET'])
    def get_redis_keys():
        """دریافت لیست کلیدهای Redis"""
        from database import get_cache
        
        db = get_cache()
        if not db or not db.is_connected():
            return jsonify({"success": False, "error": "Redis متصل نیست"}), 503
        
        try:
            keys = db._client.keys('*')
            result = []
            for key in keys:
                key_type = db._client.type(key)
                ttl = db._client.ttl(key)
                result.append({
                    'key': key,
                    'type': key_type,
                    'ttl': ttl if ttl > 0 else '∞'
                })
            
            return jsonify({
                "success": True,
                "data": result,
                "count": len(result)
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/db/search', methods=['GET'])
    def search_databases():
        """جستجوی یکپارچه در همه دیتابیس‌ها"""
        from database import get_primary, get_cache, get_backup
        
        query = request.args.get('q', '').strip()
        target = request.args.get('target', 'all')
        
        if not query or len(query) < 2:
            return jsonify({"success": False, "error": "حداقل ۲ کاراکتر وارد کنید"}), 400
        
        results = []
        
        # جستجو در PostgreSQL
        if target in ['all', 'postgresql']:
            pg = get_primary()
            if pg and pg.is_connected():
                try:
                    tables = pg.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                    for table in tables:
                        table_name = table['table_name']
                        data = pg.execute(f"SELECT * FROM {table_name} LIMIT 10")
                        for row in data:
                            if query in str(row):
                                results.append({
                                    'database': 'PostgreSQL',
                                    'type': 'table',
                                    'table': table_name,
                                    'content': str(row)[:200]
                                })
                except:
                    pass
        
        # جستجو در Redis
        if target in ['all', 'redis']:
            redis = get_cache()
            if redis and redis.is_connected():
                try:
                    keys = redis._client.keys(f'*{query}*')
                    for key in keys[:10]:
                        value = redis.get(key)
                        results.append({
                            'database': 'Redis',
                            'type': 'key',
                            'key': key,
                            'content': str(value)[:200]
                        })
                except:
                    pass
        
        return jsonify({
            "success": True,
            "data": results[:50]
        })

    # ============================================================
    # ۶. روت‌های احراز هویت
    # ============================================================
    
    @app.route('/login', methods=['POST'])
    def login():
        """ورود کاربر"""
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({"success": False, "error": "لطفاً نام کاربری و رمز عبور را وارد کنید"}), 400
        
        auth_manager = get_auth()
        result = auth_manager.login(username, password)
        
        if result["success"]:
            response = jsonify(result)
            response.set_cookie(
                'session_id', 
                result['session_id'],
                max_age=86400,
                httponly=True,
                secure=True,
                samesite='Lax',
                path='/'
            )
            return response
        
        return jsonify(result), 401

    @app.route('/logout', methods=['POST'])
    def logout():
        """خروج از حساب"""
        session_id = request.cookies.get('session_id')
        if session_id:
            auth_manager = get_auth()
            auth_manager.logout(session_id)
        
        response = jsonify({"success": True, "message": "خروج موفق"})
        response.delete_cookie('session_id', path='/')
        return response

    @app.route('/recover', methods=['POST'])
    def recover_password():
        """درخواست بازیابی رمز عبور"""
        data = request.json
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({"success": False, "error": "لطفاً ایمیل خود را وارد کنید"}), 400
        
        auth_manager = get_auth()
        username = auth_manager.get_user_by_email(email)
        
        if not username:
            return jsonify({
                "success": False, 
                "error": "ایمیل یافت نشد",
                "show_support": True,
                "support_id": "@your_telegram_id"
            }), 404
        
        code = auth_manager.generate_recovery_code(email)
        
        if code:
            return jsonify({
                "success": True,
                "message": "کد تایید به ایمیل شما ارسال شد",
                "email": email
            })
        
        return jsonify({"success": False, "error": "خطا در ارسال کد تایید"}), 500

    @app.route('/api/user', methods=['GET'])
    def get_current_user():
        """دریافت اطلاعات کاربر فعلی"""
        session_id = request.cookies.get('session_id')
        if not session_id:
            return jsonify({"success": False, "error": "وارد نشده‌اید"}), 401
        
        auth_manager = get_auth()
        session = auth_manager.verify_session(session_id)
        if not session:
            return jsonify({"success": False, "error": "نشست منقضی شده"}), 401
        
        user = auth_manager.get_user(session["username"])
        if not user:
            return jsonify({"success": False, "error": "کاربر یافت نشد"}), 404
        
        return jsonify({
            "success": True,
            "data": {
                "username": session["username"],
                "role": session.get("role", "guest"),
                "password": user.get("password", ""),
                "recovered": session.get("recovered", False),
                **user
            }
        })

    @app.route('/api/users', methods=['GET'])
    def get_users():
        """دریافت لیست کاربران (فقط ادمین)"""
        session_id = request.cookies.get('session_id')
        if not session_id:
            return jsonify({"success": False, "error": "وارد نشده‌اید"}), 401
        
        auth_manager = get_auth()
        session = auth_manager.verify_session(session_id)
        if not session:
            return jsonify({"success": False, "error": "نشست منقضی شده"}), 401
        
        if session.get("role") != "admin":
            return jsonify({"success": False, "error": "دسترسی غیرمجاز"}), 403
        
        users = auth_manager.get_all_users()
        return jsonify({"success": True, "data": users})

    # ============================================================
    # ۷. روت‌های مدیریت هشدارها
    # ============================================================
    
    @app.route('/api/alerts', methods=['GET'])
    def get_alerts():
        """دریافت هشدارهای اخیر"""
        try:
            from alerter import alerter
            limit = request.args.get('limit', 20, type=int)
            resolved = request.args.get('resolved')
            if resolved is not None:
                resolved = resolved.lower() == 'true'
            
            alerts = alerter.get_alerts(limit=limit, resolved=resolved)
            return jsonify({
                "success": True,
                "data": alerts,
                "count": len(alerts),
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            import logging
            logging.error(f"Error in get_alerts: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
    def resolve_alert(alert_id):
        """علامت‌گذاری هشدار به عنوان رفع‌شده"""
        try:
            from alerter import alerter
            success = alerter.resolve_alert(alert_id)
            return jsonify({
                "success": success,
                "message": "✅ Alert resolved" if success else "❌ Alert not found",
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            import logging
            logging.error(f"Error in resolve_alert: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/heal', methods=['POST'])
    def trigger_heal():
        """اجرای دستی خودترمیمی"""
        try:
            from self_healer import SelfHealer
            from core import metrics_scheduler
            
            self_healer = SelfHealer(system.model_manager, system.trainer)
            metrics = metrics_scheduler.get_alert_metrics()
            actions = self_healer.check_and_heal(metrics)
            return jsonify({
                "success": True,
                "actions": actions,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            import logging
            logging.error(f"Error in trigger_heal: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ============================================================
    # ۸. روت‌های تنظیمات
    # ============================================================
    
    @app.route('/api/config', methods=['GET'])
    def get_settings():
        """دریافت تمام تنظیمات سیستم"""
        try:
            from config import config as config_manager
            
            settings = config_manager.get_all()
            
            # مخفی کردن توکن‌ها
            if 'databases' in settings:
                for db_name, db_config in settings['databases'].items():
                    if 'token' in db_config:
                        token = db_config['token']
                        if token and len(token) > 10:
                            db_config['token'] = token[:6] + '...' + token[-4:]
                        else:
                            db_config['token'] = '••••••••'
            
            return jsonify({
                "success": True,
                "data": settings,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            import logging
            logging.error(f"Error getting settings: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/config', methods=['POST'])
    def update_settings():
        """به‌روزرسانی تنظیمات سیستم"""
        try:
            from config import config as config_manager
            
            data = request.json
            if not data:
                return jsonify({
                    "success": False,
                    "error": "داده ارسال نشده"
                }), 400
            
            for section, values in data.items():
                if isinstance(values, dict):
                    for key, value in values.items():
                        path = f"{section}.{key}"
                        config_manager.update(path, value)
                else:
                    config_manager.update(section, values)
            
            return jsonify({
                "success": True,
                "message": "تنظیمات با موفقیت ذخیره شد",
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            import logging
            logging.error(f"Error updating settings: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    # ============================================================
    # ۹. روت‌های دیباگ
    # ============================================================
    
    @app.route('/api/debug/exec', methods=['POST'])
    def debug_exec():
        """اجرای دستور پایتون (فقط توسعه)"""
        data = request.json
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({"success": False, "error": "دستور وارد نشده"}), 400
        
        try:
            import io
            import sys
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            
            exec(command, globals(), locals())
            
            result = sys.stdout.getvalue()
            sys.stdout = old_stdout
            
            return jsonify({
                "success": True,
                "result": result or "✅ اجرا شد (بدون خروجی)"
            })
        except Exception as e:
            sys.stdout = sys.__stdout__
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/debug/file', methods=['POST'])
    def debug_file():
        """خواندن محتوای فایل"""
        data = request.json
        filename = data.get('filename', '').strip()
        
        if not filename:
            return jsonify({"success": False, "error": "نام فایل وارد نشده"}), 400
        
        allowed_files = [
            'config/settings.json', 
            'config/databases.json', 
            'config/users.json',
            'app.py',
            'requirements.txt'
        ]
        
        if filename not in allowed_files:
            return jsonify({"success": False, "error": "دسترسی به این فایل مجاز نیست"}), 403
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({
                "success": True,
                "content": content
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    # ============================================================
    # ۱۰. روت‌های Admin
    # ============================================================
    
    @app.route('/admin/cache/clear', methods=['POST'])
    def clear_cache():
        """پاک کردن کش (فقط برای مدیریت)"""
        try:
            # پاک کردن کش API
            system.api.cache = {}
            system.api.cache_ttl = {}
            return jsonify({
                "success": True,
                "message": "کش با موفقیت پاک شد",
                "timestamp": datetime.now().isoformat()
            }), 200
        except Exception as e:
            import logging
            logging.error(f"Error clearing cache: {e}")
            return jsonify({
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500

    @app.route('/admin/db/ensure', methods=['POST'])
    def admin_ensure_db():
        """强制执行 reconnect دیتابیس‌ها (Self-Healing)"""
        try:
            from database.database_factory import db_factory
            result = db_factory.force_reconnect()
            return jsonify({
                "success": True,
                "data": result,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
