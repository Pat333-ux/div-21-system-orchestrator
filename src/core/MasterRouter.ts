export interface DivisionRoute {
  divisionId: string;
  divisionName: string;
  baseUrl: string;
  status: "ONLINE" | "OFFLINE" | "DEGRADED";
}

export class MasterRouter {
  private routes: Map<string, DivisionRoute> = new Map();

  /**
   * Register a division endpoint into the master routing table.
   */
  registerRoute(divisionId: string, divisionName: string, baseUrl: string): DivisionRoute {
    const route: DivisionRoute = {
      divisionId,
      divisionName,
      baseUrl,
      status: "ONLINE",
    };

    this.routes.set(divisionId, route);
    return route;
  }

  /**
   * Update the status of a registered division.
   */
  updateRouteStatus(divisionId: string, status: "ONLINE" | "OFFLINE" | "DEGRADED"): DivisionRoute | undefined {
    const route = this.routes.get(divisionId);
    if (!route) return undefined;

    route.status = status;
    this.routes.set(divisionId, route);
    return route;
  }

  /**
   * Retrieve routing information for a specific division.
   */
  getRoute(divisionId: string): DivisionRoute | undefined {
    return this.routes.get(divisionId);
  }

  /**
   * List all registered division routes.
   */
  getAllRoutes(): DivisionRoute[] {
    return Array.from(this.routes.values());
  }
}

export const masterRouter = new MasterRouter();
