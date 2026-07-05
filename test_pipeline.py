from dotenv import load_dotenv
load_dotenv()

import asyncio
from expense_audit_agent.agent import audit_expense_claim


async def main():
    result = await audit_expense_claim(
        claim_id="manual-test-001",
        submitter="alice@example.com",
        raw_receipt_text=(
            "Vendor: Blue Bottle Coffee\n"
            "Date: 2026-06-10\n"
            "Amount: USD 18.50\n"
            "Item: 2x coffee, 1x pastry\n"
            "Team standup catch-up with new hire."
        ),
    )
    import json
    print(json.dumps(result, indent=2, default=str))


asyncio.run(main())