import pandas as pd
from sklearn.tree import DecisionTreeClassifier
import joblib

def train_and_save():
    df = pd.read_csv('loan_data.csv')

    # Convert Loan_Type to numeric
    df['Loan_Type'] = df['Loan_Type'].astype('category').cat.codes

    X = df[['Age', 'Income', 'Loan_Amount', 'Loan_Type', 'Credit_Score']]
    y = df['Loan_Status'].map({'Approved': 1, 'Rejected': 0})

    model = DecisionTreeClassifier(max_depth=5, random_state=42)
    model.fit(X, y)

    joblib.dump(model, 'model.joblib')
    print("Model retrained successfully!")

if __name__ == "__main__":
    train_and_save()
