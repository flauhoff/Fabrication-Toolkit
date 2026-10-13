from kipy.proto.board.board_types_pb2 import BoardLayer

baseUrl = 'https://www.jlcpcb.com'

netlistFileName = 'netlist.ipc'
designatorsFileName = 'designators.csv'
placementFileName = 'positions.csv'
bomFileName = 'bom.csv'
gerberArchiveName = 'gerbers.zip'
outputFolder = 'production'
bomRowLimit = 200

optionsFileName = 'fabrication-toolkit-options.json'

standardLayers = [ BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu ] + \
                 [ BoardLayer.Value('BL_In%d_Cu' % i) for i in range(1, 31) ] + \
                 [ BoardLayer.BL_F_SilkS, BoardLayer.BL_B_SilkS,
                   BoardLayer.BL_F_Mask, BoardLayer.BL_B_Mask,
                   BoardLayer.BL_F_Paste, BoardLayer.BL_B_Paste,
                   BoardLayer.BL_Edge_Cuts
                 ]
