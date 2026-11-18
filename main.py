"""Mini NPU Simulator
Python 3.8+ / 표준 라이브러리만 사용
"""

import json

import math

import re

import time

from pathlib import Path


EPSILON = 1e-9

REPEAT_COUNT = 10


def normalize_label(label):
    """입력 라벨을 Cross 또는 X로 통일한다."""
    value = str(label).strip().lower()
    if value in ("+", "cross"):
        return "Cross"
    if value == "x":
        return "X"
    raise ValueError("알 수 없는 라벨입니다: {!r}".format(label))


def validate_matrix(matrix, expected_size=None, name="배열"):
    """2차원 숫자 배열이 정사각형인지, 값이 유효한지 검사한다."""
    if not isinstance(matrix, list) or not matrix:
        raise ValueError("{}: 비어 있거나 배열 형식이 아닙니다.".format(name))

    size = len(matrix)
    if expected_size is not None and size != expected_size:
        raise ValueError("{}: 행 크기가 {}이지만 기대 크기는 {}입니다.".format(name, size, expected_size))

    for row_index, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != size:
            raise ValueError("{}: {}번째 행의 열 개수가 올바르지 않습니다.".format(name, row_index + 1))
        for col_index, value in enumerate(row):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("{}: ({}, {}) 위치가 숫자가 아닙니다.".format(name, row_index + 1, col_index + 1))
            if not math.isfinite(float(value)):
                raise ValueError("{}: 무한대 또는 NaN은 사용할 수 없습니다.".format(name))
    return size


def mac(pattern, filter_matrix): 
    """두 배열의 같은 위치 값을 곱한 뒤 모두 더한다. (Multiply-Accumulate)"""
    size = validate_matrix(pattern, name="입력 패턴")  
    validate_matrix(filter_matrix, expected_size=size, name="필터")    

    total = 0.0
    for row in range(size):            # row 행
        for col in range(size):        # col 열
            total += float(pattern[row][col]) * float(filter_matrix[row][col])
    return total


def decide(score_cross, score_x):
    """점수 차이가 epsilon 미만이면 동점으로 판단한다."""
    if abs(score_cross - score_x) < EPSILON:
        return "UNDECIDED"
    return "Cross" if score_cross > score_x else "X"


def measure_mac(pattern, filter_matrix, repeat=REPEAT_COUNT):
    """MAC 함수만 반복 실행해 평균 시간을 밀리초로 반환한다."""
    start = time.perf_counter()
    for _ in range(repeat):
        mac(pattern, filter_matrix)
    elapsed = time.perf_counter() - start
    return (elapsed / repeat) * 1000.0


def read_matrix_from_console(name, size=3):
    """사용자로부터 행 단위로 숫자를 입력받고 잘못된 입력은 다시 받는다."""
    while True:
        print("{} ({}줄, 각 줄에 숫자 {}개)".format(name, size, size))
        matrix = []
        try:
            for row_index in range(size):
                raw = input("{}번째 행: ".format(row_index + 1)).strip().split()
                if len(raw) != size:
                    raise ValueError("각 줄에 숫자 {}개를 공백으로 구분해 입력하세요.".format(size))
                row = [float(item) for item in raw]
                if not all(math.isfinite(value) for value in row):
                    raise ValueError("유한한 숫자만 입력할 수 있습니다.")
                matrix.append(row)
            return matrix
        except ValueError as error:
            print("입력 형식 오류: {} 다시 입력해 주세요.\n".format(error))


def run_user_mode():
    print("\n[1] 필터 입력")
    filter_a = read_matrix_from_console("필터 A")
    filter_b = read_matrix_from_console("필터 B")
    print("\n[2] 패턴 입력")
    pattern = read_matrix_from_console("입력 패턴")

    score_a = mac(pattern, filter_a)
    score_b = mac(pattern, filter_b)
    elapsed_a = measure_mac(pattern, filter_a)
    elapsed_b = measure_mac(pattern, filter_b)
    result = decide(score_a, score_b)

    print("\n[3] MAC 결과")
    print("A 점수: {:.12g}".format(score_a))
    print("B 점수: {:.12g}".format(score_b))
    print("연산 시간(평균/{}회, A+B): {:.6f} ms".format(REPEAT_COUNT, elapsed_a + elapsed_b))
    print("판정: {}".format(result))
    print("※ A/B는 사용자가 입력한 필터 순서이며, JSON 모드의 Cross/X 라벨과는 별개입니다.")


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or not isinstance(data.get("filters"), dict) or not isinstance(data.get("patterns"), dict):
        raise ValueError("JSON 최상위에 filters와 patterns 객체가 있어야 합니다.")
    return data


def run_json_mode():
    path = Path(__file__).resolve().parent / "data.json"
    if not path.exists():
        print("오류: data.json 파일을 찾을 수 없습니다. main.py와 같은 폴더에 놓아 주세요.")
        return
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print("JSON 파일을 읽을 수 없습니다: {}".format(error))
        return

    filters = {}
    print("\n[1] 필터 로드")
    for size_key, filter_group in data["filters"].items():
        match = re.fullmatch(r"size_(\d+)", size_key)
        if not match:
            continue
        size = int(match.group(1))
        if not isinstance(filter_group, dict):
            print("- {}: FAIL (필터 묶음 형식 오류)".format(size_key))
            continue
        normalized = {}
        try:
            for raw_label, matrix in filter_group.items():
                label = normalize_label(raw_label)
                validate_matrix(matrix, expected_size=size, name="{} 필터".format(size_key))
                normalized[label] = matrix
            if "Cross" not in normalized or "X" not in normalized:
                raise ValueError("Cross와 X 필터가 모두 필요합니다.")
            filters[size] = normalized
            print("- {} 필터 로드 완료 (Cross, X)".format(size_key))
        except ValueError as error:
            print("- {}: FAIL ({})".format(size_key, error))

    print("\n[2] 패턴 분석")
    total = passed = failed = 0
    failures = []
    benchmark_inputs = {}

    for case_id, case in data["patterns"].items():
        total += 1
        print("\n--- {} ---".format(case_id))
        try:
            match = re.fullmatch(r"size_(\d+)_(\d+)", case_id)
            if not match:
                raise ValueError("케이스 이름이 size_N_번호 형식이 아닙니다.")
            size = int(match.group(1))
            if size not in filters:
                raise ValueError("size_{} 필터를 찾을 수 없습니다.".format(size))
            if not isinstance(case, dict) or "input" not in case or "expected" not in case:
                raise ValueError("input 또는 expected 항목이 없습니다.")

            pattern = case["input"]
            validate_matrix(pattern, expected_size=size, name="입력 패턴")
            expected = normalize_label(case["expected"])
            score_cross = mac(pattern, filters[size]["Cross"])
            score_x = mac(pattern, filters[size]["X"])
            result = decide(score_cross, score_x)
            status = "PASS" if result == expected else "FAIL"

            print("Cross 점수: {:.12g}".format(score_cross))
            print("X 점수: {:.12g}".format(score_x))
            print("판정: {} | expected: {} | {}".format(result, expected, status))
            if status == "PASS":
                passed += 1
            else:
                failed += 1
                reason = "동점(UNDECIDED) 처리" if result == "UNDECIDED" else "예상 라벨과 판정 결과 불일치"
                failures.append((case_id, reason))
            benchmark_inputs.setdefault(size, (pattern, filters[size]["Cross"]))
        except (ValueError, TypeError, KeyError) as error:
            failed += 1
            failures.append((case_id, str(error)))
            print("판정: FAIL ({})".format(error))

    print("\n[3] 성능 분석 (평균/{}회)".format(REPEAT_COUNT))
    print("크기       평균 시간(ms)       연산 횟수(N²)")
    print("---------------------------------------------")
    for size in (3, 5, 13, 25):
        if size == 3:
            sample = [[float((r + c) % 2) for c in range(3)] for r in range(3)]
            filter_matrix = [[1.0 if r == c else 0.0 for c in range(3)] for r in range(3)]
        elif size in benchmark_inputs:
            sample, filter_matrix = benchmark_inputs[size]
        elif size in filters:
            sample = [[0.0 for _ in range(size)] for _ in range(size)]
            filter_matrix = filters[size]["Cross"]
        else:
            continue
        average_ms = measure_mac(sample, filter_matrix)
        print("{:<10} {:>12.6f}       {:>8}".format("{}x{}".format(size, size), average_ms, size * size))

    print("\n[4] 결과 요약")
    print("총 테스트: {}개".format(total))
    print("통과: {}개".format(passed))
    print("실패: {}개".format(failed))
    if failures:
        print("\n실패 케이스:")
        for case_id, reason in failures:
            print("- {}: {}".format(case_id, reason))
    else:
        print("모든 테스트를 통과했습니다.")


def main():
    print("=" * 42)
    print("          Mini NPU Simulator")
    print("=" * 42)
    print("1. 사용자 입력 (3x3)")
    print("2. data.json 분석")
    choice = input("모드를 선택하세요 (1 또는 2): ").strip()
    if choice == "1":
        run_user_mode()
    elif choice == "2":
        run_json_mode()
    else:
        print("잘못된 선택입니다. 1 또는 2를 입력해 주세요.")


if __name__ == "__main__":
    main()
