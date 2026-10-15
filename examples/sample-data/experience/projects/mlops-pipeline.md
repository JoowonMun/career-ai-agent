---
title: 수요 예측 모델 배포 자동화
company: 가상물산
period: 2023.01 ~ 2023.09
role: 파이프라인 설계·구현 (2명 중 1명)
skills: [Airflow, MLflow, Docker, Kubernetes]
keywords: [MLOps, 배포, 모니터링]
essay_fit: [직무역량, 주도성, 협업]
essay_role: main
---

## 상황 (Situation)
수요 예측 모델을 분석가가 수동으로 재학습·배포해 2주가 걸렸다.

## 과제 (Task)
재학습부터 배포, 성능 모니터링까지 자동화.

## 행동 (Action)
Airflow로 재학습 파이프라인을 만들고 MLflow로 모델 버전을 관리했다. 성능이 기준 아래로 떨어지면 이전 버전으로 되돌리는 검증 단계를 넣었다.

## 결과 (Result)
배포 주기 2주 → 1일. 배포 후 성능 저하 사고 분기 3건 → 0건.

## 어필 포인트
자동 롤백 기준을 현업과 합의해 정한 점.
