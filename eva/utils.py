import datetime
import calendar
import re
import traceback

MONTH_FR_TO_NUM = {
    'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5,
    'juin': 6, 'juillet': 7, 'août': 8, 'aout': 8, 'septembre': 9,
    'octobre': 10, 'novembre': 11, 'décembre': 12
}


def parse_french_datetime(datetime_str: str):
    now = datetime.datetime.now()
    datetime_str_cleaned = datetime_str.strip().lower()

    def extract_time(text):
        time_match = re.search(r"(\d{1,2})h(?:(\d{2}))?", text, re.IGNORECASE)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            return hour, minute
        return 9, 0

    week_match = re.search(r"dans\s+(\d+|une)\s+semaine(s)?", datetime_str_cleaned)
    if week_match:
        num_weeks_str = week_match.group(1)
        num_weeks = 1 if num_weeks_str == "une" else int(num_weeks_str)
        target_date = now + datetime.timedelta(weeks=num_weeks)
        hour, minute = extract_time(datetime_str_cleaned)
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    month_match = re.search(r"dans\s+(\d+|un|une)\s+mois", datetime_str_cleaned)
    if month_match:
        num_months_str = month_match.group(1)
        num_months = 1 if num_months_str.lower() in {"un", "une"} else int(num_months_str)
        current_month = now.month
        current_year = now.year
        new_month_abs = current_month + num_months
        new_year = current_year + (new_month_abs - 1) // 12
        new_month = (new_month_abs - 1) % 12 + 1
        last_day_of_new_month = calendar.monthrange(new_year, new_month)[1]
        new_day = min(now.day, last_day_of_new_month)
        hour, minute = extract_time(datetime_str_cleaned)
        return datetime.datetime(new_year, new_month, new_day, hour, minute, second=0, microsecond=0)

    if "demain" in datetime_str_cleaned:
        target_date = now + datetime.timedelta(days=1)
        hour, minute = extract_time(datetime_str_cleaned)
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if "aujourd'hui" in datetime_str_cleaned or "ce jour" in datetime_str_cleaned:
        target_date = now
        hour, minute = extract_time(datetime_str_cleaned)
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    pattern_datetime = re.compile(
        r"(?:le\s+|l')?(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre)\s*(?:l'année\s*(\d{4})\s*)?(?:à|a)\s*(\d{1,2})h(?:(\d{2}))?",
        re.IGNORECASE,
    )
    match_datetime = pattern_datetime.search(datetime_str_cleaned)

    if match_datetime:
        day_str, month_name_fr, year_str, hour_str, minute_str = match_datetime.groups()
    else:
        pattern_date_only = re.compile(
            r"(?:le\s+|l')?(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre)\s*(?:l'année\s*(\d{4})\s*)?",
            re.IGNORECASE,
        )
        match_date_only = pattern_date_only.search(datetime_str_cleaned)
        if match_date_only:
            day_str, month_name_fr, year_str = match_date_only.groups()
            hour_str, minute_str = "9", "00"
        else:
            return None

    try:
        day = int(day_str)
        month_num = MONTH_FR_TO_NUM.get(month_name_fr.lower())
        if not month_num:
            return None
        year = int(year_str) if year_str else datetime.datetime.now().year
        hour = int(hour_str)
        minute = int(minute_str) if minute_str else 0
        if not (1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        parsed_dt = datetime.datetime(year, month_num, day, hour, minute)
        if parsed_dt < now and not year_str and (
            "prochain" in datetime_str_cleaned or "prochaine" in datetime_str_cleaned or (month_num < now.month and year == now.year)
        ):
            year += 1
            last_day = calendar.monthrange(year, month_num)[1]
            day = min(day, last_day)
            parsed_dt = datetime.datetime(year, month_num, day, hour, minute)
        return parsed_dt
    except Exception:
        traceback.print_exc()
        return None
