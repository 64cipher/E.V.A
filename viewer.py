import sys
import traceback
import pyvista as pv

def show_shape(shape_type='cube', params=None):
    """
    Affiche une forme 3D interactive en utilisant PyVista (sans animation automatique).
    """
    if params is None:
        params = [1.0]

    try:
        # Création de la forme géométrique
        if shape_type == 'cube':
            size = params[0]
            mesh = pv.Cube(center=(0, 0, 0), x_length=size, y_length=size, z_length=size)
        elif shape_type == 'sphere':
            radius = params[0] / 2.0
            mesh = pv.Sphere(radius=radius, center=(0, 0, 0))
        elif shape_type == 'cylinder':
            radius = params[0]
            height = params[1] if len(params) > 1 else radius * 2
            mesh = pv.Cylinder(center=(0, 0, 0), direction=(0, 0, 1), radius=radius, height=height)
        elif shape_type == 'cone':
            radius = params[0]
            height = params[1] if len(params) > 1 else radius * 3
            mesh = pv.Cone(center=(0, 0, height / 2), direction=(0, 0, -1), radius=radius, height=height)
        elif shape_type == 'plane':
            size = params[0]
            mesh = pv.Plane(center=(0, 0, 0), direction=(0, 0, 1), i_size=size, j_size=size)
        elif shape_type == 'torus':
            ring_radius = params[0]
            cs_radius = params[1] if len(params) > 1 else ring_radius * 0.3
            mesh = pv.ParametricTorus(ringradius=ring_radius, crosssectionradius=cs_radius)
        else:
            mesh = pv.Cube()

        # Configurer et afficher la scène de manière simple et directe
        plotter = pv.Plotter(window_size=[800, 600])
        plotter.set_background('darkslategray')
        plotter.add_mesh(mesh, color='lightblue', show_edges=True, style='surface')
        plotter.enable_shadows()
        
        print(f"Affichage d'un(e) {shape_type} avec les paramètres {params}...")
        
        # L'appel à .show() est bloquant. Le script attend ici que vous fermiez la fenêtre.
        plotter.show(title=f"Visualiseur 3D EVA - {shape_type.capitalize()}")

    except Exception as e:
        print(f"Une erreur est survenue lors de la visualisation avec PyVista: {e}")
        traceback.print_exc()
        input("Appuyez sur Entrée pour quitter...")


if __name__ == '__main__':
    shape = sys.argv[1] if len(sys.argv) > 1 else 'cube'
    
    try:
        numeric_params = [float(p) for p in sys.argv[2:]]
        if not numeric_params:
            numeric_params = [1.0]
    except ValueError:
        print("Erreur: Les paramètres après le nom de la forme doivent être des nombres.")
        numeric_params = [1.0]
    
    show_shape(shape, numeric_params)