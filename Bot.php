<?php
$token = "YOUR_BALE_TOKEN";
$chat_id = "YOUR_CHAT_ID";

// دریافت لینک
$url = $_GET['url'] ?? $_POST['url'] ?? '';
if (empty($url)) {
    die("لینک خبر یافت نشد");
}

// دریافت HTML خبر
$html = @file_get_contents($url);
if ($html === false) {
    sendMessage($chat_id, "❌ خطا در دریافت خبر", $token);
    die();
}

// استخراج تیتر (اکثر سایت‌ها از <h1> استفاده می‌کنند)
preg_match('/<h1[^>]*>(.*?)<\/h1>/i', $html, $titleMatch);
$title = $titleMatch[1] ?? "خبر";

// حذف تگ‌های HTML برای متن خالص
$html = preg_replace('/<script\b[^>]*>(.*?)<\/script>/is', '', $html);
$html = preg_replace('/<style\b[^>]*>(.*?)<\/style>/is', '', $html);
$html = preg_replace('/<nav\b[^>]*>(.*?)<\/nav>/is', '', $html);
$html = preg_replace('/<footer\b[^>]*>(.*?)<\/footer>/is', '', $html);
$html = preg_replace('/<header\b[^>]*>(.*?)<\/header>/is', '', $html);

// پیدا کردن محتوای اصلی (بر اساس تگ‌های رایج)
$content = "";

// روش 1: تگ article
if (preg_match('/<article[^>]*>(.*?)<\/article>/is', $html, $match)) {
    $content = $match[1];
}
// روش 2: div با کلاس content/body
elseif (preg_match('/<div[^>]*class="[^"]*(content|body|article|post|entry)[^"]*"[^>]*>(.*?)<\/div>/is', $html, $match)) {
    $content = $match[2];
}
// روش 3: div با id مشابه
elseif (preg_match('/<div[^>]*id="[^"]*(content|main|article)[^"]*"[^>]*>(.*?)<\/div>/is', $html, $match)) {
    $content = $match[2];
}
// روش 4: کل صفحه (آخرین راه)
else {
    $content = $html;
}

// حذف تگ‌های HTML و گرفتن متن خالص
$content = strip_tags($content);
$content = preg_replace('/\s+/', ' ', $content);
$content = trim($content);

// محدود کردن به 3500 کاراکتر
if (mb_strlen($content) > 3500) {
    $content = mb_substr($content, 0, 3500) . "...";
}

// ساخت پیام
$message = "📰 *$title*\n\n";
$message .= "$content\n\n";
$message .= "━━━━━━━━━━━━━━━━━━━━\n";
$message .= "🔗 [منبع]($url)\n";
$message .= "🤖 Fox News Bot";

// ارسال به بله
sendMessage($chat_id, $message, $token);

function sendMessage($chat_id, $text, $token) {
    $text = urlencode($text);
    @file_get_contents("https://tapi.bale.ai/bot$token/sendMessage?chat_id=$chat_id&text=$text&parse_mode=Markdown");
}
?>
