import { masterRouter } from "../core/MasterRouter";
import { eventBus } from "../core/EventBus";

export interface APIResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: string;
}

export class OrchestratorAPIHandler {
  /**
   * Register a division route in the control plane.
   * POST /api/orchestrator/routes
   */
  static registerRoute(body: {
    divisionId: string;
    divisionName: string;
    baseUrl: string;
  }): APIResponse<any> {
    if (!body.divisionId || !body.divisionName || !body.baseUrl) {
      return {
        success: false,
        error: "Missing required fields: divisionId, divisionName, or baseUrl.",
        timestamp: new Date().toISOString(),
      };
    }

    const route = masterRouter.registerRoute(body.divisionId, body.divisionName, body.baseUrl);
    return {
      success: true,
      data: route,
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * Publish a system event across the event bus.
   * POST /api/orchestrator/events
   */
  static publishEvent(body: {
    publisherDivision: string;
    eventType: string;
    payload: Record<string, any>;
  }): APIResponse<any> {
    if (!body.publisherDivision || !body.eventType) {
      return {
        success: false,
        error: "Missing required fields: publisherDivision or eventType.",
        timestamp: new Date().toISOString(),
      };
    }

    const event = eventBus.publishEvent(
      body.publisherDivision,
      body.eventType,
      body.payload || {}
    );

    return {
      success: true,
      data: event,
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * Get global ecosystem routing status.
   * GET /api/orchestrator/status
   */
  static getEcosystemStatus(): APIResponse<any> {
    const routes = masterRouter.getAllRoutes();
    const totalEvents = eventBus.getEventLog().length;

    return {
      success: true,
      data: {
        totalRegisteredDivisions: routes.length,
        totalEventsBroadcasted: totalEvents,
        routes,
      },
      timestamp: new Date().toISOString(),
    };
  }
}
