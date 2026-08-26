# Build Stage
FROM gradle:8.7-jdk21 AS builder
WORKDIR /app
COPY . .
# 실행 권한 부여 후 빌드 (테스트 생략)
RUN chmod +x ./gradlew
RUN ./gradlew clean bootJar -x test

# Run Stage
FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --from=builder /app/build/libs/*.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
