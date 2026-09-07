from pyod.models.iforest import IForest
from sklearn.metrics import classification_report,confusion_matrix,precision_recall_curve
from finlint.anomaly.dataset import build_features, load_train_test
import matplotlib.pyplot as plt

train_df,test_df=load_train_test()
X_train, X_test, y_train, y_test=build_features(train_df,test_df)

model=IForest(n_estimators=100,contamination=y_train.mean(),random_state=42)
model.fit(X_train)

pred=model.predict(X_test)
scores=model.decision_function(X_test)
print("Confusion Matrix:")
print(confusion_matrix(y_test,pred))
print("Classification Report:")
print(classification_report(y_test,pred))
print("Precision-Recall Curve:")
precision,recall,thresholds=precision_recall_curve(y_test,scores)

plt.plot(recall,precision,marker='.')
plt.xlabel('Recall')
plt.ylabel('Precision')
plt.show()
