# models/trainer/manual_trainer.py
# ============================================================
# آموزش دستی مدل - CLI
# نسخه ۲.۰
# ============================================================

import os
import sys
import argparse
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

# اضافه کردن مسیر پروژه
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from infrastructure.api.coinstats_client import CoinStatsClient
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer

logger = logging.getLogger(__name__)


# ============================================================
# Colors & Formatting
# ============================================================

class Colors:
    """رنگ‌های ANSI"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    
    BLACK = "\033[30m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


# ============================================================
# Terminal Helpers
# ============================================================

def supports_color() -> bool:
    """آیا terminal از رنگ پشتیبانی می‌کنه؟"""
    # چک متغیرهای محیطی
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    
    # اگه TTY باشه
    if hasattr(sys.stdout, "isatty"):
        return sys.stdout.isatty()
    
    return False


# اگه رنگ پشتیبانی نمی‌شه، همه رو خالی کن
if not supports_color():
    for attr in dir(Colors):
        if not attr.startswith("_"):
            setattr(Colors, attr, "")


def box_width() -> int:
    """عرض باکس (بر اساس ترمینال)"""
    try:
        return min(os.get_terminal_size().columns - 4, 70)
    except Exception:
        return 60


def print_box(
    title: str,
    lines: List[str],
    color: str = Colors.CYAN,
    icon: str = "📋",
) -> None:
    """
    چاپ باکس زیبا
    
    پارامترها:
        title: عنوان
        lines: خطوط محتوا
        color: رنگ
        icon: آیکون
    """
    width = box_width()
    
    # Top border
    print(f"\n{color}╔{'═' * width}╗{Colors.RESET}")
    
    # Title
    title_text = f"  {icon} {title}"
    padding = width - len(title_text) + 2
    print(f"{color}║{Colors.BOLD}{title_text}{' ' * padding}{color}║{Colors.RESET}")
    
    # Separator
    print(f"{color}╠{'═' * width}╣{Colors.RESET}")
    
    # Content
    for line in lines:
        # حذف ANSI برای محاسبه length
        visible_len = len(line.replace("\033[", "\\033["))
        # روش بهتر: length واقعی
        import re
        visible_len = len(re.sub(r"\033\[[0-9;]*m", "", line))
        
        padding = width - visible_len - 2
        if padding < 0:
            padding = 0
        
        print(f"{color}║{Colors.RESET} {line}{' ' * padding} {color}║{Colors.RESET}")
    
    # Bottom border
    print(f"{color}╚{'═' * width}╝{Colors.RESET}\n")


def print_header(title: str, icon: str = "🚀") -> None:
    """چاپ header"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'═' * box_width()}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}  {icon}  {title}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'═' * box_width()}{Colors.RESET}\n")


def print_success(msg: str) -> None:
    """چاپ پیام موفق"""
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")


def print_error(msg: str) -> None:
    """چاپ پیام خطا"""
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")


def print_warning(msg: str) -> None:
    """چاپ پیام هشدار"""
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")


def print_info(msg: str) -> None:
    """چاپ پیام اطلاعاتی"""
    print(f"{Colors.CYAN}ℹ️  {msg}{Colors.RESET}")


def print_dim(msg: str) -> None:
    """چاپ پیام کم‌رنگ"""
    print(f"{Colors.DIM}{msg}{Colors.RESET}")


def print_separator(char: str = "─", color: str = Colors.DIM) -> None:
    """چاپ جداکننده"""
    print(f"{color}{char * box_width()}{Colors.RESET}")


def print_kv(key: str, value: Any, icon: str = "•") -> None:
    """چاپ کلید-مقدار"""
    print(f"  {icon} {Colors.BOLD}{key}:{Colors.RESET} {value}")


def print_progress(
    current: int,
    total: int,
    prefix: str = "",
    width: int = 30,
) -> None:
    """
    چاپ progress bar
    
    پارامترها:
        current: مقدار فعلی
        total: مقدار کل
        prefix: پیشوند
        width: عرض
    """
    if total == 0:
        percent = 0
    else:
        percent = current / total
    
    filled = int(width * percent)
    bar = "█" * filled + "░" * (width - filled)
    
    # رنگ بر اساس درصد
    if percent < 0.33:
        color = Colors.RED
    elif percent < 0.66:
        color = Colors.YELLOW
    else:
        color = Colors.GREEN
    
    print(
        f"\r  {prefix} {color}[{bar}]{Colors.RESET} "
        f"{Colors.BOLD}{percent * 100:.1f}%{Colors.RESET}",
        end="",
        flush=True,
    )


def format_duration(seconds: float) -> str:
    """فرمت مدت زمان"""
    if seconds < 60:
        return f"{seconds:.1f} ثانیه"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes} دقیقه و {secs} ثانیه"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours} ساعت و {minutes} دقیقه"


def format_percent(value: float) -> str:
    """فرمت درصد با رنگ"""
    percent = value * 100
    if percent >= 75:
        color = Colors.GREEN
    elif percent >= 60:
        color = Colors.CYAN
    elif percent >= 45:
        color = Colors.YELLOW
    else:
        color = Colors.RED
    return f"{color}{percent:.2f}%{Colors.RESET}"


# ============================================================
# Logging Setup
# ============================================================

def setup_logging(verbose: bool = False) -> None:
    """راه‌اندازی logging"""
    # در CLI، لاگ‌ها رو کم می‌کنیم
    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        # فقط WARNING و بالاتر
        logging.basicConfig(
            level=logging.WARNING,
            format="%(levelname)s: %(message)s",
        )
        
        # کم کردن لاگ کتابخانه‌ها
        for name in ["urllib3", "requests", "xgboost"]:
            logging.getLogger(name).setLevel(logging.ERROR)


# ============================================================
# Setup Dependencies
# ============================================================

def setup_dependencies() -> Tuple[CoinStatsClient, ModelManager, AutoTrainer]:
    """
    ساخت dependency ها
    
    خروجی:
        (api, model_manager, trainer)
    """
    with print_status("در حال ساخت dependencies"):
        api = CoinStatsClient()
        model_manager = ModelManager(api)
        trainer = AutoTrainer(api, model_manager)
    
    return api, model_manager, trainer


class print_status:
    """Context manager برای نمایش وضعیت"""
    
    def __init__(self, message: str):
        self.message = message
        self.start = 0
    
    def __enter__(self):
        print(f"  {Colors.DIM}⏳ {self.message}...{Colors.RESET}", end="", flush=True)
        self.start = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start
        if exc_type is None:
            print(
                f"\r  {Colors.GREEN}✅{Colors.RESET} "
                f"{self.message} "
                f"{Colors.DIM}({duration:.2f}s){Colors.RESET}"
            )
        else:
            print(
                f"\r  {Colors.RED}❌{Colors.RESET} "
                f"{self.message} "
                f"{Colors.DIM}(failed){Colors.RESET}"
            )
        return False  # propagate exception


# ============================================================
# Commands: Train
# ============================================================

def cmd_train(args: argparse.Namespace) -> int:
    """
    آموزش مدل
    
    پارامترها:
        args: namespace از argparse
    
    خروجی:
        exit code (0 = موفق)
    """
    try:
        # Setup
        api, model_manager, trainer = setup_dependencies()
        
        # Parse coins
        coins = None
        if args.coins:
            coins = [c.strip() for c in args.coins.split(",") if c.strip()]
        
        # نمایش header
        print_header("شروع آموزش مدل", icon="🚀")
        
        # نمایش پارامترها
        print(f"  {Colors.BOLD}پارامترها:{Colors.RESET}")
        print_kv("Period", args.period, "📅")
        print_kv("Profile", args.profile or "active", "🎯")
        print_kv("Strategy", args.strategy or "from profile", "🔄")
        print_kv("Coins", coins or "default", "🪙")
        print_kv("Save", "No" if args.no_save else "Yes", "💾")
        print()
        
        # Time tracking
        start_time = time.time()
        
        # آموزش
        print(f"  {Colors.CYAN}🔄 شروع آموزش...{Colors.RESET}\n")
        
        result = trainer.train_model(
            period=args.period,
            coins=coins,
            profile_name=args.profile,
            strategy=args.strategy,
            save=not args.no_save,
        )
        
        total_time = time.time() - start_time
        
        # نمایش نتیجه
        print()
        print_result(result, total_time)
        
        # نمایش لاگ‌های trainer
        if args.verbose:
            print()
            print(f"  {Colors.BOLD}📋 لاگ‌ها:{Colors.RESET}")
            for log in trainer.get_logs()[-15:]:
                print(f"  {Colors.DIM}{log}{Colors.RESET}")
        
        return 0 if result.get("success") else 1
    
    except KeyboardInterrupt:
        print()
        print_warning("عملیات توسط کاربر متوقف شد")
        return 130
    
    except Exception as e:
        print()
        print_error(f"خطای غیرمنتظره: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def print_result(result: Dict[str, Any], total_time: float) -> None:
    """
    نمایش نتیجه آموزش
    
    پارامترها:
        result: نتیجه از AutoTrainer
        total_time: زمان کل
    """
    if result.get("success"):
        # موفق
        version = result.get("version", "N/A")
        accuracy = result.get("accuracy", 0)
        samples = result.get("samples", 0)
        strategy = result.get("strategy_used", "N/A")
        profile = result.get("profile_used", "N/A")
        
        lines = [
            f"Version:    {Colors.BOLD}{version}{Colors.RESET}",
            f"Accuracy:   {format_percent(accuracy)}",
            f"Samples:    {samples:,}",
            f"Strategy:   {strategy}",
            f"Profile:    {profile}",
            f"Total time: {format_duration(total_time)}",
        ]
        
        # اگه improvement هست
        if "improvement" in result and result["improvement"] is not None:
            imp = result["improvement"]
            imp_pct = imp * 100
            if imp_pct > 0:
                lines.append(
                    f"Improvement: {Colors.GREEN}+{imp_pct:.2f}%{Colors.RESET}"
                )
            else:
                lines.append(
                    f"Improvement: {Colors.RED}{imp_pct:.2f}%{Colors.RESET}"
                )
        
        print_box(
            "آموزش با موفقیت انجام شد",
            lines,
            color=Colors.GREEN,
            icon="✅",
        )
    
    else:
        # خطا
        error = result.get("error", "خطای ناشناخته")
        message = result.get("message", "")
        
        lines = [
            f"Error:   {Colors.RED}{error}{Colors.RESET}",
        ]
        
        if message:
            lines.append(f"Message: {message}")
        
        # اگه details هست
        details = result.get("details", [])
        if details:
            lines.append("")
            lines.append(f"{Colors.BOLD}جزئیات:{Colors.RESET}")
            for detail in details[:5]:
                lines.append(f"  • {detail}")
        
        print_box(
            "آموزش ناموفق",
            lines,
            color=Colors.RED,
            icon="❌",
        )


# ============================================================
# Commands: List Presets
# ============================================================

def cmd_list_presets(model_manager: ModelManager) -> int:
    """لیست presets"""
    try:
        presets = model_manager.get_presets()
        
        if not presets:
            print_warning("هیچ preset یافت نشد")
            return 0
        
        print_header("Training Presets", icon="📋")
        
        for preset in presets:
            hp = preset.get("hyperparameters", {})
            n_est = hp.get("n_estimators", "?")
            depth = hp.get("max_depth", "?")
            lr = hp.get("learning_rate", "?")
            
            print(f"  {preset.get('icon', '•')}  {Colors.BOLD}{preset['id']}{Colors.RESET}")
            print(f"     {Colors.DIM}{preset.get('description', '')}{Colors.RESET}")
            print(
                f"     {Colors.CYAN}n_estimators={n_est}{Colors.RESET}, "
                f"{Colors.CYAN}max_depth={depth}{Colors.RESET}, "
                f"{Colors.CYAN}lr={lr}{Colors.RESET}"
            )
            est = preset.get("estimated_time_seconds", "?")
            print(f"     {Colors.DIM}⏱  ~{est}s{Colors.RESET}")
            print()
        
        print_info(f"کل: {len(presets)} preset")
        return 0
    
    except Exception as e:
        print_error(f"خطا: {e}")
        return 1


# ============================================================
# Commands: List Strategies
# ============================================================

def cmd_list_strategies(model_manager: ModelManager) -> int:
    """لیست استراتژی‌ها"""
    try:
        strategies = model_manager.get_strategies()
        
        if not strategies:
            print_warning("هیچ استراتژی یافت نشد")
            return 0
        
        print_header("Learning Strategies", icon="📋")
        
        for strategy in strategies:
            requires = strategy.get("requires_existing_model", False)
            req_text = (
                f"{Colors.YELLOW}(نیاز به مدل موجود){Colors.RESET}"
                if requires
                else f"{Colors.GREEN}(بدون نیاز به مدل){Colors.RESET}"
            )
            
            print(f"  {strategy.get('icon', '•')}  {Colors.BOLD}{strategy['id']}{Colors.RESET}")
            print(f"     {Colors.DIM}{strategy.get('description', '')}{Colors.RESET}")
            print(f"     {req_text}")
            print()
        
        print_info(f"کل: {len(strategies)} استراتژی")
        return 0
    
    except Exception as e:
        print_error(f"خطا: {e}")
        return 1


# ============================================================
# Commands: List Saved Profiles
# ============================================================

def cmd_list_saved_profiles(model_manager: ModelManager) -> int:
    """لیست پروفایل‌های ذخیره‌شده"""
    try:
        profiles = model_manager.list_profiles()
        
        if not profiles:
            print_info("هیچ پروفایل ذخیره‌شده‌ای یافت نشد")
            print_dim(
                "  برای ذخیره پروفایل، از فرانت‌اند یا "
                "model_manager.save_profile() استفاده کن."
            )
            return 0
        
        print_header("Saved Profiles", icon="💾")
        
        for profile in profiles:
            hp = profile.get("hyperparameters", {})
            n_est = hp.get("n_estimators", "?")
            depth = hp.get("max_depth", "?")
            strategy = profile.get("learning_strategy", "full")
            
            print(f"  {profile.get('icon', '⚙️')}  {Colors.BOLD}{profile['name']}{Colors.RESET}")
            
            if profile.get("description"):
                print(f"     {Colors.DIM}{profile['description']}{Colors.RESET}")
            
            print(
                f"     {Colors.CYAN}n_est={n_est}{Colors.RESET}, "
                f"{Colors.CYAN}depth={depth}{Colors.RESET}, "
                f"{Colors.CYAN}strategy={strategy}{Colors.RESET}"
            )
            
            updated = profile.get("updated_at", "")
            if updated:
                print(f"     {Colors.DIM}🕐 آخرین بروزرسانی: {updated[:19]}{Colors.RESET}")
            
            print()
        
        print_info(f"کل: {len(profiles)} پروفایل")
        return 0
    
    except Exception as e:
        print_error(f"خطا: {e}")
        return 1


# ============================================================
# Commands: Show Stats
# ============================================================

def cmd_show_stats(trainer: AutoTrainer) -> int:
    """نمایش آمار"""
    try:
        stats = trainer.get_stats()
        
        print_header("آمار AutoTrainer", icon="📊")
        
        # وضعیت
        print(f"  {Colors.BOLD}وضعیت:{Colors.RESET}")
        print_kv("Running", "✅ Yes" if stats.get("is_running") else "❌ No", "🔄")
        print_kv("Training", "✅ Yes" if stats.get("is_training") else "❌ No", "🎓")
        
        stats_inner = stats.get("stats", {})
        print_kv("Mode", stats_inner.get("mode", "DEMO"), "⚙️")
        print()
        
        # آموزش
        print(f"  {Colors.BOLD}آموزش:{Colors.RESET}")
        print_kv("Total trainings", stats_inner.get("total_trainings", 0), "📚")
        print_kv("Successful", stats_inner.get("successful_trainings", 0), "✅")
        print_kv("Failed", stats_inner.get("failed_trainings", 0), "❌")
        
        last_score = stats_inner.get("last_score")
        if last_score:
            print_kv("Last score", format_percent(last_score), "🎯")
        
        last_training = stats_inner.get("last_training")
        if last_training:
            print_kv("Last training", last_training[:19], "🕐")
        print()
        
        # API
        api_status = stats.get("api_status", {})
        print(f"  {Colors.BOLD}API:{Colors.RESET}")
        status_icon = "✅" if api_status.get("api_status") == "ok" else "❌"
        print_kv("Status", f"{status_icon} {api_status.get('api_status', 'unknown')}", "🌐")
        print_kv("Credits", api_status.get("credits_remaining", 0), "💰")
        print()
        
        # مدل
        print(f"  {Colors.BOLD}مدل:{Colors.RESET}")
        print_kv("Loaded", "✅ Yes" if stats.get("model_exists") else "❌ No", "📦")
        print_kv("Version", stats.get("current_version", "N/A"), "🏷️")
        print()
        
        # Quota
        quota = stats.get("quota", {})
        if quota:
            print(f"  {Colors.BOLD}Quota:{Colors.RESET}")
            used = quota.get("used_mb", 0)
            usable = quota.get("usable_mb", 0)
            percent = quota.get("used_percent", 0)
            print_kv("Used", f"{used:.2f} MB / {usable:.2f} MB", "💾")
            print_kv("Percent", f"{percent:.1f}%", "📊")
            print_kv("Status", quota.get("status", "unknown"), "🎯")
        
        return 0
    
    except Exception as e:
        print_error(f"خطا: {e}")
        return 1


# ============================================================
# Commands: Show History
# ============================================================

def cmd_show_history(trainer: AutoTrainer, limit: int = 10) -> int:
    """نمایش تاریخچه"""
    try:
        history = trainer.get_training_history(limit=limit)
        
        if not history:
            print_info("هیچ تاریخچه‌ای یافت نشد")
            return 0
        
        print_header("تاریخچه آموزش", icon="📜")
        
        # Header
        header = (
            f"  {Colors.BOLD}"
            f"{'Version':<25} "
            f"{'Accuracy':<12} "
            f"{'Samples':<10} "
            f"{'Date':<20}"
            f"{Colors.RESET}"
        )
        print(header)
        print_separator()
        
        # Rows
        for item in history:
            version = (item.get("version", "N/A") or "N/A")[:22]
            accuracy = item.get("accuracy", 0) or 0
            samples = item.get("training_samples", 0) or 0
            date = item.get("training_date", "")
            
            if date:
                date_str = date[:19] if isinstance(date, str) else date.strftime("%Y-%m-%d %H:%M:%S")
            else:
                date_str = "N/A"
            
            # رنگ accuracy
            acc_pct = accuracy * 100
            if acc_pct >= 75:
                acc_color = Colors.GREEN
            elif acc_pct >= 60:
                acc_color = Colors.CYAN
            elif acc_pct >= 45:
                acc_color = Colors.YELLOW
            else:
                acc_color = Colors.RED
            
            # active marker
            is_active = item.get("is_active", False)
            active_marker = f"{Colors.GREEN}*{Colors.RESET}" if is_active else " "
            
            print(
                f"{active_marker} "
                f"{version:<25} "
                f"{acc_color}{acc_pct:>6.2f}%{Colors.RESET}     "
                f"{samples:>8,} "
                f"{Colors.DIM}{date_str}{Colors.RESET}"
            )
        
        print()
        print_info(f"کل: {len(history)} رکورد  (* = فعال)")
        return 0
    
    except Exception as e:
        print_error(f"خطا: {e}")
        return 1


# ============================================================
# Commands: Batch Train (A/B Testing)
# ============================================================

def cmd_batch_train(args: argparse.Namespace) -> int:
    """A/B Testing چند پروفایل"""
    try:
        # Setup
        api, model_manager, trainer = setup_dependencies()
        
        # Parse profiles
        profiles = [p.strip() for p in args.batch.split(",") if p.strip()]
        
        if len(profiles) < 2:
            print_error("برای A/B Testing حداقل ۲ پروفایل لازمه")
            return 1
        
        # Parse coins
        coins = None
        if args.coins:
            coins = [c.strip() for c in args.coins.split(",") if c.strip()]
        
        # Header
        print_header("A/B Testing", icon="🧪")
        print(f"  {Colors.BOLD}پروفایل‌ها:{Colors.RESET} {', '.join(profiles)}")
        print(f"  {Colors.BOLD}Period:{Colors.RESET} {args.period}")
        if coins:
            print(f"  {Colors.BOLD}Coins:{Colors.RESET} {', '.join(coins)}")
        print()
        
        # شروع
        start_time = time.time()
        
        result = trainer.train_batch(
            profiles=profiles,
            period=args.period,
            coins=coins,
        )
        
        total_time = time.time() - start_time
        
        # نمایش نتایج
        print()
        print_batch_results(result, total_time)
        
        return 0 if result.get("success") else 1
    
    except KeyboardInterrupt:
        print()
        print_warning("عملیات توسط کاربر متوقف شد")
        return 130
    
    except Exception as e:
        print_error(f"خطا: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def print_batch_results(result: Dict[str, Any], total_time: float) -> None:
    """نمایش نتایج A/B Testing"""
    if not result.get("success"):
        print_error(f"A/B Testing ناموفق: {result.get('error', 'خطای ناشناخته')}")
        return
    
    results = result.get("results", {})
    best_profile = result.get("best_profile")
    best_accuracy = result.get("best_accuracy", 0)
    
    # جدول نتایج
    print(f"  {Colors.BOLD}{'Profile':<15} {'Accuracy':<15} {'Status':<10}{Colors.RESET}")
    print_separator()
    
    for profile_name, prof_result in results.items():
        if prof_result.get("success"):
            acc = prof_result.get("accuracy", 0)
            acc_str = format_percent(acc)
            status = f"{Colors.GREEN}✅ OK{Colors.RESET}"
            
            # نشانه‌گذاری بهترین
            star = " ⭐" if profile_name == best_profile else ""
            
            print(f"  {profile_name:<15} {acc_str:<15} {status}{star}")
        else:
            error = prof_result.get("error", "unknown")[:20]
            print(f"  {profile_name:<15} {Colors.RED}FAILED{Colors.RESET}         {error}")
    
    print()
    
    # بهترین
    if best_profile:
        lines = [
            f"Best Profile: {Colors.BOLD}{best_profile}{Colors.RESET}",
            f"Accuracy:     {format_percent(best_accuracy)}",
            f"Total time:   {format_duration(total_time)}",
            f"Profiles:     {len(results)}",
        ]
        
        print_box(
            "نتیجه A/B Testing",
            lines,
            color=Colors.GREEN,
            icon="🏆",
        )


# ============================================================
# Argparse Setup
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    """ساخت parser"""
    parser = argparse.ArgumentParser(
        prog="train_model",
        description="آموزش دستی مدل XGBoost",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
مثال‌ها:
  # آموزش ساده
  python scripts/train_model.py --period 1m

  # آموزش با پروفایل
  python scripts/train_model.py --period 1m --profile accurate

  # آموزش با استراتژی
  python scripts/train_model.py --period 1m --strategy incremental

  # آموزش با ارزهای خاص
  python scripts/train_model.py --coins bitcoin,ethereum,solana

  # A/B Testing
  python scripts/train_model.py --batch fast,balanced,accurate

  # لیست پروفایل‌های آماده
  python scripts/train_model.py --list-presets

  # لیست استراتژی‌ها
  python scripts/train_model.py --list-strategies

  # لیست پروفایل‌های ذخیره‌شده
  python scripts/train_model.py --list-saved-profiles

  # آمار
  python scripts/train_model.py --stats

  # تاریخچه
  python scripts/train_model.py --history --limit 10
""",
    )
    
    # === آموزش ===
    train_group = parser.add_argument_group("آموزش")
    train_group.add_argument(
        "--period",
        type=str,
        default="1m",
        choices=["24h", "1w", "1m", "3m", "6m"],
        help="بازه داده (پیش‌فرض: 1m)",
    )
    train_group.add_argument(
        "--profile",
        type=str,
        default=None,
        help="نام پروفایل (preset یا ذخیره‌شده)",
    )
    train_group.add_argument(
        "--strategy",
        type=str,
        default=None,
        choices=["full", "incremental", "transfer", "fine_tune", "ensemble"],
        help="استراتژی آموزش (override)",
    )
    train_group.add_argument(
        "--coins",
        type=str,
        default=None,
        help="لیست ارزها (جدا با کاما): bitcoin,ethereum",
    )
    train_group.add_argument(
        "--no-save",
        action="store_true",
        help="مدل ذخیره نشه (فقط آموزش)",
    )
    
    # === A/B Testing ===
    batch_group = parser.add_argument_group("A/B Testing")
    batch_group.add_argument(
        "--batch",
        type=str,
        default=None,
        help="لیست پروفایل‌ها برای A/B Testing: fast,balanced,accurate",
    )
    
    # === دستورات کمکی ===
    info_group = parser.add_argument_group("اطلاعات")
    info_group.add_argument(
        "--list-presets",
        action="store_true",
        help="لیست پروفایل‌های آماده",
    )
    info_group.add_argument(
        "--list-strategies",
        action="store_true",
        help="لیست استراتژی‌های یادگیری",
    )
    info_group.add_argument(
        "--list-saved-profiles",
        action="store_true",
        help="لیست پروفایل‌های ذخیره‌شده",
    )
    info_group.add_argument(
        "--stats",
        action="store_true",
        help="نمایش آمار",
    )
    info_group.add_argument(
        "--history",
        action="store_true",
        help="نمایش تاریخچه آموزش",
    )
    info_group.add_argument(
        "--limit",
        type=int,
        default=10,
        help="تعداد رکورد برای --history (پیش‌فرض: 10)",
    )
    
    # === عمومی ===
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="نمایش جزئیات بیشتر",
    )
    
    return parser


# ============================================================
# Main
# ============================================================

def main() -> int:
    """
    ورودی اصلی
    
    خروجی:
        exit code
    """
    parser = build_parser()
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Banner
    if not args.verbose:
        print()
        print(
            f"{Colors.CYAN}{Colors.BOLD}"
            f"  🚀 Trading Signal System - Manual Trainer v2.0"
            f"{Colors.RESET}"
        )
    
    try:
        # ===== Dispatch =====
        
        # دستورات اطلاعاتی (بدون dependency سنگین)
        if args.list_presets or args.list_strategies or args.list_saved_profiles:
            try:
                api = CoinStatsClient()
                model_manager = ModelManager(api)
            except Exception as e:
                print_error(f"خطا در ساخت ModelManager: {e}")
                return 1
            
            if args.list_presets:
                return cmd_list_presets(model_manager)
            if args.list_strategies:
                return cmd_list_strategies(model_manager)
            if args.list_saved_profiles:
                return cmd_list_saved_profiles(model_manager)
        
        # دستورات آماری
        if args.stats or args.history:
            try:
                api = CoinStatsClient()
                model_manager = ModelManager(api)
                trainer = AutoTrainer(api, model_manager)
            except Exception as e:
                print_error(f"خطا در ساخت dependencies: {e}")
                return 1
            
            if args.stats:
                return cmd_show_stats(trainer)
            if args.history:
                return cmd_show_history(trainer, args.limit)
        
        # A/B Testing
        if args.batch:
            return cmd_batch_train(args)
        
        # آموزش پیش‌فرض
        return cmd_train(args)
    
    except KeyboardInterrupt:
        print()
        print_warning("عملیات توسط کاربر متوقف شد")
        return 130
    
    except Exception as e:
        print()
        print_error(f"خطای غیرمنتظره: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
