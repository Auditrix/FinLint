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

def build_features(train_df, test_df):

    X_train=train_df[['debit_amount', 'credit_amount', 'local_amount', 'exchange_rate', 'gl_account', 'fiscal_year','document_type','is_post_close','gap']]
    X_test=test_df[['debit_amount', 'credit_amount', 'local_amount', 'exchange_rate', 'gl_account', 'fiscal_year','document_type','is_post_close','gap']]
        
    X_train=pd.get_dummies(X_train,columns=['document_type','gap'])
    X_test=pd.get_dummies(X_test,columns=['document_type','gap'])
    X_test=X_test.reindex(columns=X_train.columns, fill_value=0)
    
    y_train=train_df[TARGET_COLUMN]
    y_test=test_df[TARGET_COLUMN]
    
    return X_train, X_test, y_train, y_test

