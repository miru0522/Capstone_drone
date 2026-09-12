# Build Stage
FROM gradle:8.7-jdk21 AS builder
WORKDIR /app
COPY . .
# 실행 권한 부여 후 빌드 (테스트 생략)
RUN chmod +x ./gradlew
# gradle 본체(래퍼가 받는 8.14, 약 130MB)와 라이브러리를 빌드 사이에 재사용한다.
# 위의 COPY 가 소스가 바뀔 때마다 캐시를 깨서, 전에는 빌드마다 전부 새로 받았다
# (2026-09-11 다운로드가 느려 한 번에 10분 넘게 걸렸다).
# 이미지 기본값(/home/gradle/.gradle)에 기대지 않고 캐시 위치와 같은 곳을 직접 지정한다.
ENV GRADLE_USER_HOME=/cache/gradle
RUN --mount=type=cache,target=/cache/gradle ./gradlew clean bootJar -x test

# Run Stage
FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --from=builder /app/build/libs/*.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
