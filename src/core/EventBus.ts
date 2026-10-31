export interface SystemEvent {
  eventId: string;
  publisherDivision: string;
  eventType: string;
  payload: Record<string, any>;
  timestamp: string;
}

export class EventBus {
  private eventLog: SystemEvent[] = [];

  /**
   * Broadcast an event from one division across the network.
   */
  publishEvent(
    publisherDivision: string,
    eventType: string,
    payload: Record<string, any>
  ): SystemEvent {
    const event: SystemEvent = {
      eventId: `EVT-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
      publisherDivision,
      eventType,
      payload,
      timestamp: new Date().toISOString(),
    };

    this.eventLog.push(event);
    return event;
  }

  /**
   * Get all published system events.
   */
  getEventLog(): SystemEvent[] {
    return this.eventLog;
  }

  /**
   * Filter events by publisher division.
   */
  getEventsByDivision(divisionName: string): SystemEvent[] {
    return this.eventLog.filter((e) => e.publisherDivision === divisionName);
  }
}

export const eventBus = new EventBus();
