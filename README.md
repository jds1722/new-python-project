# 8-plane TIFF Channel Extractor

입력 폴더의 멀티레이어 TIFF에서 배열 index `0`, `1`, `2`, `5`, `6`을 각각 단일-plane TIFF로 추출하는 Windows GUI입니다.

기본 출력 filename:

- `원본이름_BF.tif` (index 0)
- `원본이름_Nuclei.tif` (index 1)
- `원본이름_Plane2.tif` (index 2)
- `원본이름_Bead5.tif` (index 5)
- `원본이름_Plane6.tif` (index 6)

index 2와 6의 suffix를 포함한 모든 suffix는 UI에서 변경할 수 있습니다. 원본 TIFF는 수정하지 않으며 처리 결과는 `extraction_report.csv`에 기록됩니다.

## 실행

실행 환경이 구성되어 있으므로 `run.bat`을 더블클릭합니다.
