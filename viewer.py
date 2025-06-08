import sys
import traceback
import pyvista as pv
import os

def show_shape(shape_type='cube', params=None):
    """
    Affiche une forme 3D, soit en la générant, soit en chargeant un modèle
    depuis le dossier /models.
    """
    if params is None:
        params = [1.0]

    try:
        mesh = None
        model_found = False

        if shape_type == 'model':
            model_name = params[0]
            supported_extensions = ['.stl', '.obj', '.ply'] # Ajoutez d'autres formats si besoin
            
            for ext in supported_extensions:
                file_path = os.path.join('models', f"{model_name}{ext}")
                if os.path.exists(file_path):
                    mesh = pv.read(file_path)
                    model_found = True
                    print(f"Chargement du modèle : {file_path}")
                    break
            
            if not model_found:
                print(f"Erreur: Modèle '{model_name}' non trouvé dans le dossier 'models'. Affichage d'un cube par défaut.")
                mesh = pv.Cube()

        elif shape_type == 'cube':
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
            print(f"Erreur: Type de forme non reconnu '{shape_type}'. Affichage d'un cube par défaut.")
            mesh = pv.Cube()

        # Configurer la scène de visualisation
        plotter = pv.Plotter(window_size=[800, 600])
        plotter.set_background('darkslategray')

        actor = plotter.add_mesh(mesh, color='lightblue', show_edges=True, style='surface')
        
        plotter.enable_shadows()
        
        print(f"Affichage d'un(e) {shape_type}...")
        
        # Le .show() est bloquant. La rotation manuelle avec la souris est activée par défaut.
        plotter.show(title=f"Visualiseur 3D EVA - {shape_type.capitalize()}", auto_close=False)

    except Exception as e:
        print(f"Une erreur est survenue lors de la visualisation avec PyVista: {e}")
        traceback.print_exc()
        input("Appuyez sur Entrée pour quitter...")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python viewer.py <shape_type> [params...]")
        sys.exit(1)
        
    shape = sys.argv[1]
    
    # Le traitement des paramètres dépend du type de forme
    if shape == 'model':
        if len(sys.argv) < 3:
            print("Usage pour 'model': python viewer.py model <model_name>")
            sys.exit(1)
        params = sys.argv[2:] # Les paramètres sont des chaînes de caractères (noms de fichiers)
    else:
        # Pour les formes primitives, les paramètres sont numériques
        try:
            params = [float(p) for p in sys.argv[2:]]
            if not params:
                params = [1.0]
        except ValueError:
            print("Erreur: Les paramètres pour les formes primitives doivent être des nombres.")
            params = [1.0]
    
    show_shape(shape, params)
