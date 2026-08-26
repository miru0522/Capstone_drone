package com.drone.backend.config;// WebConfig.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {
    @Value("${app.video.storage-dir}")
    private String storageDir;

    @Value("${app.profile.storage-dir:./profiledata}")
    private String profileStorageDir;

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        // http://<host[:port]>/media/<파일명> 으로 접근 (app.video.storage-dir 기준)
        // [수정 2026-08-05] storageDir이 주입만 되고 쓰이지 않던 것을 실제로 배선했다.
        // 설정 기본값(./videodata)이 기존 하드코딩값과 같으므로 동작은 변하지 않는다.
        registry.addResourceHandler("/media/**")
                .addResourceLocations(
                        toLocation(storageDir),
                        "file:" + System.getProperty("user.dir") + "/videodata/")
                .setCachePeriod(3600);
                
        // wavdata 폴더 제공
        registry.addResourceHandler("/wavdata/**")
                .addResourceLocations("file:./wavdata/")
                .setCachePeriod(3600);

        // 프로필 사진 제공 (/profile/<파일명>)
        // 사진을 바꾸면 파일명(UUID)이 달라지므로 캐시를 길게 잡아도 갱신이 즉시 반영된다.
        registry.addResourceHandler("/profile/**")
                .addResourceLocations(toLocation(profileStorageDir))
                .setCachePeriod(86400);
    }

    /** 설정값을 Spring 리소스 로케이션 형식("file:.../")으로 정규화한다. */
    private String toLocation(String dir) {
        String normalized = dir.replace('\\', '/');
        if (!normalized.endsWith("/")) {
            normalized += "/";
        }
        return normalized.startsWith("file:") ? normalized : "file:" + normalized;
    }

    @Override
    public void addCorsMappings(org.springframework.web.servlet.config.annotation.CorsRegistry registry) {
        registry.addMapping("/**")
                .allowedOriginPatterns("*")
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
                .allowedHeaders("*")
                .allowCredentials(true);
    }
}