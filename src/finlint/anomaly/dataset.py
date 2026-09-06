import pandas as pd
from pathlib import Path

TARGET_COLUMN = 'is_fraud'
LEAKAGE_COLUMNS= ['fraud_type','anomaly_type']

def load_train_test():
    root=Path(__file__).parents[3]
    train_df=pd.read_parquet(root/'data'/'training'/'vynfi'/'train.parquet')
    test_df=pd.read_parquet(root/'data'/'training'/'vynfi'/'test.parquet')
    
    train_df.drop(columns=['auxiliary_account_number', 'auxiliary_account_label', 'lettrage', 'lettrage_date', 'tax_code'], inplace=True)
    test_df.drop(columns=['auxiliary_account_number', 'auxiliary_account_label', 'lettrage', 'lettrage_date', 'tax_code'], inplace=True)
    return train_df,test_df

