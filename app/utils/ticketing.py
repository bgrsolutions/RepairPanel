from datetime import datetime


def generate_ticket_number(branch_code: str, sequence: int) -> str:
    date_part = datetime.utcnow().strftime("%Y%m%d")
    return f"{branch_code}-{date_part}-{sequence:05d}"
