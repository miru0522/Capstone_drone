package com.drone.backend.event;

import java.util.Map;
import lombok.Getter;
import org.springframework.context.ApplicationEvent;

@Getter
public class DroneCommandEvent extends ApplicationEvent {
    private final String droneId;
    private final Map<String, Object> command;

    public DroneCommandEvent(Object source, String droneId, Map<String, Object> command) {
        super(source);
        this.droneId = droneId;
        this.command = command;
    }
}
