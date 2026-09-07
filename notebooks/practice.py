from pyod.models.iforest import IForest
from pyod.utils.data import generate_data
from sklearn.metrics import classification_report

contamination = 0.1 
X_train,X_test,y_train,y_test=generate_data(n_train=200,n_test=100,contamination=contamination,random_state=42)
model=IForest(contamination=contamination,random_state=42)
model.fit(X_train)

pred=model.labels_
scores=model.decision_scores_

test_pred=model.predict(X_test)
test_scores=model.decision_function(X_test)

"""print(f"Train predictions: {pred}")
print(f"Train scores: {scores}")
print(f"Test predictions: {test_pred}")
print(f"Test scores: {test_scores}")
"""
report=classification_report(y_test,test_pred)
result=classification_report(y_train,pred)

print(report)
print(result)