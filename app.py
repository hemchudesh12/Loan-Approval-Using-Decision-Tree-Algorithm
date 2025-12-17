
from flask import Flask, render_template, request, redirect, url_for
import csv
import os
from datetime import datetime
import math

app = Flask(__name__)

CSV_FILE = "loan_applications.csv"

# Maximum amount allowed per loan category
LOAN_LIMITS = {
    "Home": 5000000,       # ₹50,00,000
    "Personal": 500000,    # ₹5,00,000
    "Car": 2000000,        # ₹20,00,000
    "Education": 2000000,  # ₹20,00,000
    "Business": 3000000    # ₹30,00,000
}

# Default tenure in years if user does not specify or old data
DEFAULT_TENURE_YEARS = 5


def calculate_emi(principal, annual_rate, tenure_years):
    """Calculate EMI based on principal, annual interest rate and tenure in years."""
    try:
        principal = float(principal)
        annual_rate = float(annual_rate)
        tenure_years = float(tenure_years)
    except (TypeError, ValueError):
        return 0.0

    n = int(tenure_years * 12)
    if n <= 0:
        return 0.0

    r = annual_rate /(12.0 * 100.0)
    if r == 0:
        return round(principal / n, 2)

    emi = principal * r * (1 + r) ** n / ((1 + r) ** n - 1)
    return round(emi, 2)


def base_interest_rate(loan_type, credit_score):
    """Simple mapping of interest rates by type + score."""
    base_rates = {
        "Home": 5.2,
        "Personal": 7.5,
        "Car": 7.0,
        "Education": 4.8,
        "Business": 8.5
    }
    rate = base_rates.get(loan_type, 10.0)

    # Reward higher scores with slightly lower interest
    if credit_score >= 780:
        rate -= 0.7
    elif credit_score >= 730:
        rate -= 0.4
    elif credit_score >= 680:
        rate -= 0.1
    elif credit_score < 600:
        rate += 1.0

    return round(max(rate, 5.0), 2)


def evaluate_application(name, age, income, loan_amount, loan_type,
                         employment, existing_debt, tenure_years):
    """Apply business rules, credit score logic, category limits and EMI."""
    # Convert numeric values safely
    age = int(age)
    income = float(income)
    loan_amount = float(loan_amount)
    existing_debt = float(existing_debt)
    tenure_years = float(tenure_years) if tenure_years else DEFAULT_TENURE_YEARS

    remarks = []
    exceeded_limit = False

    # Check category-wise loan limit
    max_allowed = LOAN_LIMITS.get(loan_type)
    if max_allowed is not None and loan_amount > max_allowed:
        exceeded_limit = True
        remarks.append(
            f"Requested amount exceeds maximum limit for {loan_type} loans (₹{int(max_allowed):,})."
        )

    # Debt-to-income ratio (simple)
    total_debt = existing_debt + loan_amount
    debt_to_income = (existing_debt / income) * 100 if income > 0 else 0

    # Basic credit scoring logic
    credit_score = 650

    # DTI factor
    if debt_to_income < 20:
        credit_score += 80
        remarks.append("Excellent debt-to-income ratio.")
    elif debt_to_income < 35:
        credit_score += 40
        remarks.append("Good debt-to-income ratio.")
    elif debt_to_income < 50:
        credit_score += 10
        remarks.append("Moderate debt-to-income ratio.")
    else:
        credit_score -= 60
        remarks.append("High debt-to-income ratio.")

    # Employment type
    emp_lower = employment.lower()
    if "salaried" in emp_lower or "employee" in emp_lower:
        credit_score += 30
        remarks.append("Stable salaried employment.")
    elif "self" in emp_lower:
        credit_score += 10
        remarks.append("Self-employed.")
    elif "unemployed" in emp_lower:
        credit_score -= 40
        remarks.append("Currently unemployed.")

    # Loan-to-income relationship
    if loan_amount <= income * 5:
        credit_score += 20
        remarks.append("Requested amount is reasonable compared to income.")
    elif loan_amount > income * 10:
        credit_score -= 30
        remarks.append("Requested amount is high compared to income.")

    # Age band
    if 25 <= age <= 55:
        credit_score += 10
    elif age < 21:
        credit_score -= 20
        remarks.append("Very young age – limited credit history.")
    elif age > 60:
        credit_score -= 15
        remarks.append("Near retirement age.")

    # Final decision rules
    if exceeded_limit:
        decision = "Rejected"
        remarks.append("Application rejected due to category limit.")
    elif credit_score >= 700 and debt_to_income <= 45:
        decision = "Approved"
        remarks.append("Credit score and DTI within acceptable range.")
    else:
        decision = "Rejected"
        remarks.append("Score or DTI outside acceptable range.")

    # Interest and EMI only if approved
    interest_rate = base_interest_rate(loan_type, credit_score)
    emi = calculate_emi(loan_amount, interest_rate, tenure_years) if decision == "Approved" else 0.0

    # Human-friendly remarks string
    remarks_text = " ".join(remarks)

    decision_data = {
        "name": name,
        "age": age,
        "income": income,
        "loan_amount": loan_amount,
        "loan_type": loan_type,
        "employment": employment,
        "existing_debt": existing_debt,
        "tenure_years": tenure_years,
        "debt_to_income": round(debt_to_income, 2),
        "credit_score": int(credit_score),
        "decision": decision,
        "interest_rate": interest_rate,
        "emi": emi,
        "remarks": remarks_text,
        "max_allowed": max_allowed
    }
    return decision_data


NEW_HEADER = [
    "Name",
    "Age",
    "Income",
    "Loan_Amount",
    "Loan_Type",
    "Tenure_Years",
    "Employment",
    "Existing_Debt",
    "Debt_to_Income",
    "Credit_Score",
    "InterestRate",
    "EMI",
    "Loan_Status",
    "DateApplied",
    "Remarks",
    "Decision"
]


def migrate_csv_if_needed():
    """Upgrade old CSV (without EMI & tenure) to new schema."""
    if not os.path.exists(CSV_FILE):
        return

    with open(CSV_FILE, newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return  # empty file

    # If already migrated, do nothing
    if "Tenure_Years" in header or "EMI" in header:
        return

    # Read old data as DictReader
    with open(CSV_FILE, newline="") as f:
        old_reader = csv.DictReader(f)
        rows = list(old_reader)

    upgraded_rows = []
    for row in rows:
        try:
            loan_amount = float(row.get("Loan_Amount") or 0)
            rate = float(row.get("InterestRate") or 0)
        except ValueError:
            loan_amount = 0
            rate = 0

        tenure = DEFAULT_TENURE_YEARS
        emi = calculate_emi(loan_amount, rate, tenure)

        upgraded_rows.append({
            "Name": row.get("Name", ""),
            "Age": row.get("Age", ""),
            "Income": row.get("Income", ""),
            "Loan_Amount": row.get("Loan_Amount", ""),
            "Loan_Type": row.get("Loan_Type", ""),
            "Tenure_Years": tenure,
            "Employment": row.get("Employment", ""),
            "Existing_Debt": row.get("Existing_Debt", "") or 0,
            "Debt_to_Income": row.get("Debt_to_Income", "") or "",
            "Credit_Score": row.get("Credit_Score", ""),
            "InterestRate": row.get("InterestRate", ""),
            "EMI": emi,
            "Loan_Status": row.get("Loan_Status", row.get("Decision", "")),
            "DateApplied": row.get("DateApplied", ""),
            "Remarks": row.get("Remarks", ""),
            "Decision": row.get("Decision", row.get("Loan_Status", ""))
        })

    # Overwrite CSV with new header + upgraded rows
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=NEW_HEADER)
        writer.writeheader()
        for r in upgraded_rows:
            writer.writerow(r)


def read_all_applications():
    """Return list of dict rows from CSV in new schema."""
    if not os.path.exists(CSV_FILE):
        return []

    migrate_csv_if_needed()

    with open(CSV_FILE, newline="") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader]
    return rows


@app.route("/")
def dashboard():
    """Main dashboard with summary cards."""
    rows = read_all_applications()

    total = len(rows)
    approved = sum(1 for r in rows if (r.get("Loan_Status") or "").lower() == "approved")
    rejected = sum(1 for r in rows if (r.get("Loan_Status") or "").lower() == "rejected")

    total_disbursed = 0.0
    for r in rows:
        if (r.get("Loan_Status") or "").lower() == "approved":
            try:
                total_disbursed += float(r.get("Loan_Amount") or 0)
            except ValueError:
                pass

    # Per-loan-type stats
    loan_type_stats = {}
    for r in rows:
        lt = r.get("Loan_Type", "Unknown")
        status = (r.get("Loan_Status") or "").title() or "Unknown"
        loan_type_stats.setdefault(lt, {"total": 0, "approved": 0, "rejected": 0})
        loan_type_stats[lt]["total"] += 1
        if status == "Approved":
            loan_type_stats[lt]["approved"] += 1
        elif status == "Rejected":
            loan_type_stats[lt]["rejected"] += 1

    summary = {
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "total_disbursed": int(total_disbursed)
    }

    return render_template(
        "index.html",
        summary=summary,
        loan_limits=LOAN_LIMITS,
        loan_type_stats=loan_type_stats,
    )


@app.route("/apply")
def apply():
    """Loan application form UI."""
    return render_template("form.html", loan_limits=LOAN_LIMITS)


@app.route("/submit", methods=["POST"])
def submit():
    """Handle loan submission and show decision with EMI details."""
    name = request.form.get("name")
    age = request.form.get("age")
    income = request.form.get("income")
    loan_amount = request.form.get("loan_amount")
    loan_type = request.form.get("loan_type")
    employment = request.form.get("employment")
    existing_debt = request.form.get("existing_debt") or 0
    tenure_years = request.form.get("tenure_years") or DEFAULT_TENURE_YEARS

    decision_data = evaluate_application(
        name=name,
        age=age,
        income=income,
        loan_amount=loan_amount,
        loan_type=loan_type,
        employment=employment,
        existing_debt=existing_debt,
        tenure_years=tenure_years
    )

    # Ensure CSV exists & migrated
    migrate_csv_if_needed()

    # Append new row in the new schema
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_row = {
        "Name": decision_data["name"],
        "Age": decision_data["age"],
        "Income": decision_data["income"],
        "Loan_Amount": decision_data["loan_amount"],
        "Loan_Type": decision_data["loan_type"],
        "Tenure_Years": decision_data["tenure_years"],
        "Employment": decision_data["employment"],
        "Existing_Debt": decision_data["existing_debt"],
        "Debt_to_Income": decision_data["debt_to_income"],
        "Credit_Score": decision_data["credit_score"],
        "InterestRate": decision_data["interest_rate"],
        "EMI": decision_data["emi"],
        "Loan_Status": decision_data["decision"],
        "DateApplied": now_str,
        "Remarks": decision_data["remarks"],
        "Decision": decision_data["decision"],
    }

    file_exists = os.path.exists(CSV_FILE)
    write_header = not file_exists or os.path.getsize(CSV_FILE) == 0

    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=NEW_HEADER)
        if write_header:
            writer.writeheader()
        writer.writerow(new_row)

    return render_template("result.html", data=decision_data)


@app.route("/approved")
def approved():
    """View approved applications with EMI details."""
    rows = read_all_applications()
    approved_rows = [r for r in rows if (r.get("Loan_Status") or "").lower() == "approved"]
    return render_template("approved.html", loans=approved_rows)


@app.route("/rejected")
def rejected():
    """View rejected applications."""
    rows = read_all_applications()
    rejected_rows = [r for r in rows if (r.get("Loan_Status") or "").lower() == "rejected"]
    return render_template("rejected.html", loans=rejected_rows)


@app.route("/stats")
def stats():
    """Dynamic statistics page with Chart.js (pie + bar)."""
    rows = read_all_applications()

    # Overall status counts
    approved = sum(1 for r in rows if (r.get("Loan_Status") or "").lower() == "approved")
    rejected = sum(1 for r in rows if (r.get("Loan_Status") or "").lower() == "rejected")

    # Loan type distribution
    type_counts = {}
    type_approved = {}
    type_rejected = {}

    for r in rows:
        lt = r.get("Loan_Type", "Unknown") or "Unknown"
        status = (r.get("Loan_Status") or "").title() or "Unknown"

        type_counts[lt] = type_counts.get(lt, 0) + 1
        if status == "Approved":
            type_approved[lt] = type_approved.get(lt, 0) + 1
        elif status == "Rejected":
            type_rejected[lt] = type_rejected.get(lt, 0) + 1

    loan_types = sorted(type_counts.keys())
    counts = [type_counts[lt] for lt in loan_types]
    approved_counts = [type_approved.get(lt, 0) for lt in loan_types]
    rejected_counts = [type_rejected.get(lt, 0) for lt in loan_types]

    status_counts = {
        "approved": approved,
        "rejected": rejected,
        "total": len(rows)
    }

    return render_template(
        "stats.html",
        loan_types=loan_types,
        counts=counts,
        approved_counts=approved_counts,
        rejected_counts=rejected_counts,
        status_counts=status_counts,
        loan_limits=LOAN_LIMITS
    )


if __name__ == "__main__":
    app.run(debug=True)
